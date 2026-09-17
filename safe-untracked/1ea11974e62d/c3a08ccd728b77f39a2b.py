"""Disposable Git and read-only HTTP fixtures; no model/app/provider startup."""
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.charlie.native_runner.canonical_client import GitHubObserver
from modules.charlie.native_runner.execution import NativeExecutionError
from modules.charlie.native_runner.service import NativeRunnerService
from scripts import charlie_render_native_runner as bootstrap


def git(root,*args):
    return subprocess.run(['git',*args],cwd=root,text=True,capture_output=True,check=True).stdout.strip()


def repository(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    git(root,'init');git(root,'config','user.name','Disposable test');git(root,'config','user.email','test@example.invalid')
    target=root/'demo.txt';target.write_text('before\n')
    git(root,'add','.');git(root,'commit','-m','synthetic base')
    git(root,'remote','add','origin',bootstrap.ORIGIN)
    return root,target,git(root,'rev-parse','HEAD')


@pytest.mark.parametrize('kind',['unstaged','staged','untracked'])
def test_bootstrap_preserves_dirty_primary_before_fetch_or_checkout(tmp_path,monkeypatch,kind):
    root,target,head=repository(tmp_path)
    if kind=='untracked':target=root/'retained-user-file.txt'
    target.write_bytes(b'preserve exactly\r\n')
    if kind=='staged':git(root,'add',target.name)
    before=target.read_bytes();status=git(root,'status','--porcelain')
    monkeypatch.setattr(bootstrap,'DISK',tmp_path)
    monkeypatch.setattr(bootstrap,'REPOSITORY',root)
    monkeypatch.setattr(bootstrap,'WORKTREES',tmp_path/'worktrees')
    monkeypatch.setattr(bootstrap,'PROFILE',tmp_path/'profile')
    real=bootstrap.run;calls=[]
    def run(argv,**kw):
        calls.append(argv)
        assert argv[1] not in {'fetch','checkout','clone'}
        return real(argv,**kw)
    monkeypatch.setattr(bootstrap,'run',run)
    with pytest.raises(RuntimeError,match='repository_dirty'):bootstrap.prepare_repository(deployed_sha=head)
    assert target.read_bytes()==before and git(root,'rev-parse','HEAD')==head
    assert git(root,'status','--porcelain')==status


@pytest.mark.parametrize('committed',[False,True])
def test_retained_patch_intent_recovers_staged_and_committed_content(tmp_path,committed):
    root,target,head=repository(tmp_path)
    target.write_text('after\n')
    patch=subprocess.run(['git','diff','--binary','--no-ext-diff','--'],cwd=root,
                         text=True,capture_output=True,check=True).stdout
    sha=hashlib.sha256(patch.encode()).hexdigest()
    record={'schema':'charlie_native_patch_intent_v1','patch':patch,'patch_sha256':sha,
            'changed_files':['demo.txt'],'builder_identity':'HNW-FAKE','starting_head':head}
    (root.parent/'.native-1-correction-patch-intent.json').write_text(json.dumps(record))
    auth={'correction_patch_sha256':sha,'correction_builder_identity':'HNW-FAKE'}
    git(root,'add','demo.txt')
    if committed:git(root,'commit','-m','synthetic correction')
    service=object.__new__(NativeRunnerService)
    recovered=service._recover_patch_intent(auth,root,stage='correction')
    assert recovered==record
    if committed:
        target.write_text('unproven user change\n')
        with pytest.raises(NativeExecutionError,match='unproven_changes'):
            service._recover_patch_intent(auth,root,stage='correction')
        assert target.read_text()=='unproven user change\n'


def check_fixture():
    repo={'full_name':'Crewless9086/amadeus-pig-tracking-system'}
    pull={'number':17,'state':'open','draft':True,'head':{'sha':'b'*40,'repo':repo},'base':{'ref':'main','repo':repo}}
    rows=[{'id':i+1,'name':name,'head_sha':'b'*40,'status':'completed','conclusion':'success',
           'app':{'id':4742997 if name=='mission-admission' else 15368},
           'details_url':'https://github.com/'+repo['full_name']+'/actions/runs/123'}
          for i,name in enumerate(sorted(GitHubObserver.REQUIRED))]
    return pull,{'check_runs':rows,'total_count':len(rows)}


@pytest.mark.parametrize('fault',['none','wrong-head','untrusted-app','incomplete','running','duplicate','foreign-details','wrong-pr'])
def test_complete_trusted_check_contract(fault):
    pull,checks=check_fixture()
    if fault=='wrong-head':checks['check_runs'][0]['head_sha']='c'*40
    if fault=='untrusted-app':checks['check_runs'][0]['app']['id']=999
    if fault=='incomplete':checks['total_count']+=1
    if fault=='running':checks['check_runs'][0]['status']='in_progress'
    if fault=='duplicate':checks['check_runs'].append(copy.deepcopy(checks['check_runs'][0]));checks['total_count']+=1
    if fault=='foreign-details':checks['check_runs'][0]['details_url']='https://example.invalid/untrusted'
    if fault=='wrong-pr':pull['number']=18
    client=SimpleNamespace(request=lambda method,path,**kw:pull if '/pulls/' in path else checks)
    observer=GitHubObserver(client=client)
    if fault in {'incomplete','wrong-pr'}:
        with pytest.raises(NativeExecutionError):observer.pull_state(17)
    else:assert observer.pull_state(17)['all_required_checks_pass'] is (fault=='none')


@pytest.mark.parametrize('fault',['none','closed','wrong-pr','foreign-repo'])
def test_packager_retains_exact_existing_pr(fault):
    from modules.charlie.native_runner.execution import NativePackager
    packager=object.__new__(NativePackager);packager._expected_pull_number=17
    repo={'full_name':'Crewless9086/amadeus-pig-tracking-system'}
    pull={'number':17,'state':'open','draft':True,'head':{'ref':'charlie/fake','sha':'b'*40,'repo':repo},
          'base':{'ref':'main','repo':repo}}
    if fault=='closed':pull['state']='closed'
    if fault=='wrong-pr':pull['number']=18
    if fault=='foreign-repo':pull['head']['repo']={'full_name':'untrusted/fork'}
    calls=[]
    packager._github=lambda method,path:calls.append((method,path)) or pull
    if fault=='none':assert packager._find_pull('charlie/fake')==pull
    else:
        with pytest.raises(NativeExecutionError):packager._find_pull('charlie/fake')
    assert calls==[('GET','/repos/Crewless9086/amadeus-pig-tracking-system/pulls/17')]


@pytest.mark.parametrize('fault',['none','evidence-argv','plan-name'])
def test_governed_executable_verification_packaging_to_actual_content_review(tmp_path,monkeypatch,fault):
    from datetime import datetime,timedelta,timezone
    from modules.charlie.native_runner.execution import NativeExecutionEngine,NativePackager,NativeAuthorization
    from modules.charlie.native_runner.review_packet import build_review_packet
    root,target,_=repository(tmp_path)
    (root/'test_synthetic.py').write_text('import unittest\nclass Proof(unittest.TestCase):\n def test_outcome(self): self.assertEqual(2+2,4)\n')
    git(root,'add','test_synthetic.py');git(root,'commit','-m','disposable executable verification fixture')
    base=git(root,'rev-parse','HEAD');git(root,'checkout','-b','charlie/synthetic-native-1')
    instruction='Document the synthetic owner boundary.'
    native={'mission_id':'CHARLIE-MISSION-LOCAL-TEST','generation':'g1','native_execution_id':'HNX-FAKE',
        'native_attempt':1,'repository':'Crewless9086/amadeus-pig-tracking-system','starting_main_sha':base,
        'branch':'charlie/synthetic-native-1','worktree_digest':'a'*64,
        'owner_instruction_digest':hashlib.sha256(instruction.encode()).hexdigest(),
        'allowed_files':['demo.txt'],'allowed_commands':['git status','git diff','git diff --check'],
        'allowed_effects':['edit_allowed_files'],'forbidden_effects':['merge','deploy'],'forbidden_files':['.env*'],
        'status':'valid','expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    plan=[{'name':'synthetic executable test','argv':['python','-m','unittest','test_synthetic','-q']}]
    target.write_text('After: owner approval required.\n')
    engine=object.__new__(NativeExecutionEngine);engine.authorization=NativeAuthorization.from_mapping(native)
    engine.worktree=SimpleNamespace(worktree_root=root);engine.heartbeat=lambda:None;engine.verification_plan=plan
    evidence=engine.verify()
    assert len(evidence)==4 and evidence[-1]['returncode']==0
    remote={'head':'','pull':None};calls=[]
    class Recovery:
        canonical=SimpleNamespace(mission=lambda _:{'mission':{'metadata':{}}})
        def perform(self,kind,intent,call,evidence,**kw):
            result=call();assert evidence(result,intent)['identity']==intent['identity'];return result
    packager=NativePackager(root,native,'fake-only',recovery=Recovery())
    def github(method,path,payload=None,**kw):
        calls.append((method,path))
        if '/git/ref/' in path:
            return {'ref':'refs/heads/'+native['branch'],'object':{'sha':remote['head']}} if remote['head'] else None
        if method=='GET':return [remote['pull']] if remote['pull'] else []
        repo={'full_name':native['repository']}
        remote['pull']={'number':17,'draft':True,'state':'open','head':{'sha':remote['head'],'ref':native['branch'],'repo':repo},
                        'base':{'ref':'main','repo':repo},'html_url':'https://example.invalid/synthetic/17'}
        return remote['pull']
    packager._github=github
    packager._push_with_ephemeral_askpass=lambda:remote.update(head=git(root,'rev-parse','HEAD'))
    packaged=packager.package('synthetic source candidate','labelled fake remote provider')
    native.update(pr_number=packaged['pr_number'],head_sha=packaged['commit_sha'],
                  candidate_diff_sha256=packaged['candidate_diff_sha256'],changed_files=packaged['changed_files'])
    mission={'mission_id':native['mission_id'],'metadata':{'mission_vault':{'problem_statement':instruction,
        'test_plan':['synthetic executable test'],'acceptance_criteria':['Document the owner boundary.']}}}
    if fault=='evidence-argv':evidence[-1]['argv']=['python','-m','unittest','different_test']
    if fault=='plan-name':plan[0]['name']='invented verification'
    if fault!='none':
        with pytest.raises(NativeExecutionError):build_review_packet(root,mission,native,evidence,verification_plan=plan)
    else:
        packet=build_review_packet(root,mission,native,evidence,verification_plan=plan)
        assert packet['content']['files'][0]['after']=='After: owner approval required.\n'
        assert packet['candidate']['head_sha']==git(root,'rev-parse','HEAD')
        assert packet['executable_verification_plan']==plan
    assert sum(method=='POST' for method,_ in calls)==1
