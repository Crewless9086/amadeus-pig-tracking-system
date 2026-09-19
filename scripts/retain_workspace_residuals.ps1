#requires -Version 7.0
<#
Intact local retention only. PLAN is default; -Apply renames exact approved
top-level roots on one NTFS volume. No child enumeration, deletion, copying,
ACL changes or provider calls. Nested links remain opaque and may require
restoration to their original absolute paths. Source writers must be stopped.
#>
[CmdletBinding()]
param(
 [Parameter(Mandatory)][string]$Plan,
 [Parameter(Mandatory)][string]$OutcomeLog,
 [switch]$Apply,
 [string]$TestFixtureRoot
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if(-not $IsWindows){throw 'Windows_required'}
Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.IO;
using System.Numerics;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;
public sealed class RetainInfo {
 public string Device, Inode; public uint Attributes, Tag;
}
public static class RetainNative {
 [StructLayout(LayoutKind.Sequential)] struct Id {public ulong Volume, Low, High;}
 [StructLayout(LayoutKind.Sequential)] struct Tag {public uint Attributes, Value;}
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 static extern SafeFileHandle CreateFileW(string p,uint a,uint s,IntPtr sec,uint c,uint f,IntPtr t);
 [DllImport("kernel32.dll",SetLastError=true,EntryPoint="GetFileInformationByHandleEx")]
 static extern bool ReadId(SafeFileHandle h,int k,out Id v,uint n);
 [DllImport("kernel32.dll",SetLastError=true,EntryPoint="GetFileInformationByHandleEx")]
 static extern bool ReadTag(SafeFileHandle h,int k,out Tag v,uint n);
 [DllImport("kernel32.dll",SetLastError=true)]
 static extern bool SetFileInformationByHandle(SafeFileHandle h,int k,IntPtr v,uint n);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 static extern bool GetVolumePathNameW(string p,StringBuilder volume,uint size);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 static extern bool GetVolumeInformationW(string root,StringBuilder name,uint namesize,
  out uint serial,out uint maxlen,out uint flags,StringBuilder fs,uint fssize);
 static void Check(bool ok){if(!ok)throw new Win32Exception(Marshal.GetLastWin32Error());}
 public static string Native(string p){return p.StartsWith(@"\\?\")?p:(p.StartsWith(@"\\")?@"\\?\UNC\"+p.Substring(2):@"\\?\"+p);}
 public static SafeFileHandle Open(string p,bool move){
  var h=CreateFileW(Native(p),move?0x10080u:0x80u,move?3u:7u,IntPtr.Zero,3,0x02000000|0x00200000,IntPtr.Zero);
  if(h.IsInvalid){int e=Marshal.GetLastWin32Error();h.Dispose();throw new Win32Exception(e);}return h;
 }
 public static RetainInfo Handle(SafeFileHandle h){
  Id id;Tag tag;Check(ReadId(h,18,out id,(uint)Marshal.SizeOf<Id>()));
  Check(ReadTag(h,9,out tag,(uint)Marshal.SizeOf<Tag>()));
  return new RetainInfo {Device=id.Volume.ToString(),Inode=(((BigInteger)id.High<<64)|id.Low).ToString(),Attributes=tag.Attributes,Tag=tag.Value};
 }
 public static RetainInfo Info(string p){using(var h=Open(p,false))return Handle(h);}
 public static bool Exists(string p){
  try{Info(p);return true;}catch(Win32Exception e){if(e.NativeErrorCode==2||e.NativeErrorCode==3)return false;throw;}
 }
 public static void NoReparse(string p){
  var chain=new System.Collections.Generic.Stack<string>();
  while(!String.IsNullOrEmpty(p)){
   chain.Push(p);string parent=Path.GetDirectoryName(p);if(parent==p)break;p=parent;
  }
  while(chain.Count>0)if((Info(chain.Pop()).Attributes&0x400)!=0)throw new IOException("reparse_root_or_ancestor");
 }
 public static void Ntfs(string p){
  var volume=new StringBuilder(32768);Check(GetVolumePathNameW(Native(p),volume,(uint)volume.Capacity));
  var fs=new StringBuilder(64);uint a,b,c;
  Check(GetVolumeInformationW(volume.ToString(),null,0,out a,out b,out c,fs,(uint)fs.Capacity));
  if(!String.Equals(fs.ToString(),"NTFS",StringComparison.OrdinalIgnoreCase))throw new IOException("ntfs_required");
 }
 public static void Rename(SafeFileHandle h,string destination){
  // FILE_RENAME_INFO: ReplaceIfExists=false; null-terminated UTF-16 name.
  // No recursive processing or overwrite; FileNameLength excludes its terminator.
  byte[] name=Encoding.Unicode.GetBytes(Native(destination));
  int rootOffset=IntPtr.Size==8?8:4, lengthOffset=rootOffset+IntPtr.Size;
  int nameOffset=lengthOffset+4, size=nameOffset+name.Length+2;
  IntPtr buffer=Marshal.AllocHGlobal(size);
  try{
   for(int i=0;i<size;i++)Marshal.WriteByte(buffer,i,0);
   Marshal.WriteInt32(buffer,lengthOffset,name.Length);
   Marshal.Copy(name,0,IntPtr.Add(buffer,nameOffset),name.Length);
   Check(SetFileInformationByHandle(h,3,buffer,(uint)size));
  }finally{Marshal.FreeHGlobal(buffer);}
 }
}
'@
function Full([string]$Value){
 if(-not [IO.Path]::IsPathFullyQualified($Value) -or $Value.StartsWith('\\?\') -or
  $Value -match '[*?]' -or $Value.Substring(2).Contains(':')){throw 'resolved_absolute_path_required'}
 $p=[IO.Path]::GetFullPath($Value).TrimEnd('\')
 if($p.Length -le 3 -or $p -cne $Value.TrimEnd('\')){throw 'resolved_absolute_path_required'};return $p
}
function Inside([string]$Path,[string]$Root){
 return $Path.Equals($Root,[StringComparison]::OrdinalIgnoreCase) -or $Path.StartsWith($Root+'\',[StringComparison]::OrdinalIgnoreCase)
}
function Same($A,$B){return $A.Device -eq $B.Device -and $A.Inode -eq $B.Inode -and $A.Attributes -eq $B.Attributes -and $A.Tag -eq $B.Tag}
function Reason($Record){
 $e=$Record.Exception;while($e.InnerException){$e=$e.InnerException}
 if($e.Message -match '^[a-z_]+$'){return $e.Message}
 if($e -is [ComponentModel.Win32Exception]){return 'win32_'+$e.NativeErrorCode};return $e.GetType().Name
}
$locks=[Collections.Generic.List[IDisposable]]::new()
function Lock([string]$Path){
 $Path=Full $Path;[RetainNative]::NoReparse($Path)
 $locks.Add([IO.FileStream]::new([RetainNative]::Native($Path),[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read))
 return $Path
}
function Json([string]$Path){return [IO.File]::ReadAllText([RetainNative]::Native($Path))|ConvertFrom-Json -AsHashtable}
function Hash([string]$Path){return (Get-FileHash -LiteralPath ([RetainNative]::Native($Path)) -Algorithm SHA256).Hash.ToLowerInvariant()}
$log=$null
try{
 $Plan=Lock $Plan;$OutcomeLog=Full $OutcomeLog;$config=Json $Plan
 if($config.version -ne 1 -or $config.intact_retention_only -ne $true -or
  $config.writers_stopped -ne $true -or -not $config.owner_authorization -or -not $config.roots){
  throw 'explicit_intact_retention_authority_required'
 }
 $sources=@{agents='C:\Users\charl\OneDrive\1. Amadeus\AGENTS';tmp='C:\tmp'}
 $recovery='C:\Amadeus\recovery\20260919'
 $original='C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system'
 if($TestFixtureRoot){
  $fixture=Full $TestFixtureRoot
  if([IO.Path]::GetDirectoryName($fixture) -ne 'C:\Amadeus\.runtime\retention-tests' -or
   [IO.Path]::GetFileName($fixture) -notmatch '^[a-f0-9]{32}$'){throw 'synthetic_fixture_scope_required'}
  $sources=@{agents=(Join-Path $fixture 'agents');tmp=(Join-Path $fixture 'tmp')}
  $recovery=Join-Path $fixture 'recovery';$original=Join-Path $sources.agents 'amadeus-pig-tracking-system'
 }
 foreach($p in @($sources.Values)+@($recovery)){[RetainNative]::NoReparse($p);[RetainNative]::Ntfs($p)}
 foreach($p in $sources.Values){if(Inside $OutcomeLog $p){throw 'outcome_inside_sources'}}
 if(Inside $OutcomeLog (Join-Path $recovery 'retained-originals')){throw 'outcome_inside_retained_roots'}
 [RetainNative]::NoReparse([IO.Path]::GetDirectoryName($OutcomeLog))
 $classificationPath=Lock ([string]$config.classification_manifest)
 if((Hash $classificationPath) -ne $config.classification_sha256){throw 'classification_digest_mismatch'}
 $classification=Json $classificationPath
 $candidates=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::OrdinalIgnoreCase)
 $uncertain=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::OrdinalIgnoreCase)
 foreach($r in $classification.allowlist_candidates){$candidates.Add((Full ([string]$r.path)),$r)}
 foreach($r in $classification.held_entries){$uncertain.Add((Full ([string]$r.path)),$r)}
 $covered=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 foreach($run in $config.retirement_runs){
  $allowPath=Lock ([string]$run.allowlist);$runPath=Lock ([string]$run.outcome_log);$allow=Json $allowPath
  if($allow.version -ne 1 -or -not $allow.owner_authorization -or $allow.writers_stopped -ne $true){throw 'invalid_retirement_authority'}
  $reader=[IO.StreamReader]::new([RetainNative]::Native($runPath));$first=$null;$last=$null;$count=0
  try{
   while($null -ne ($line=$reader.ReadLine())){
    $row=$line|ConvertFrom-Json -AsHashtable;$count++
    if($count -eq 1){$first=$row}
    if($row.ContainsKey('action') -and $row.action -in @('removal_pending','directory_removal_pending')){throw 'pending_disposition_rejected'}
    if($row.ContainsKey('status') -and $row.status -notin @('PASS','HOLDS_REMAIN')){throw 'incomplete_retirement_rejected'}
    $last=$row
   }
  }finally{$reader.Dispose()}
  if($count -lt 2 -or $first.kind -ne 'start' -or $first.mode -ne 'APPLY' -or
   $first.allowlist_sha256 -ne (Hash $allowPath) -or $last.mode -ne 'APPLY' -or
   $last.status -notin @('PASS','HOLDS_REMAIN') -or -not $last.finished_at -or
   $last.archive_sha256 -ne $first.archive_sha256 -or $last.manifest_sha256 -ne $first.manifest_sha256 -or
   $last.totals.removal_pending -ne 0 -or $last.totals.directory_removal_pending -ne 0){throw 'completed_apply_required'}
  foreach($r in $allow.roots){
   if($r.disposition -ne 'obsolete-amadeus-copy' -or -not $r.ownership_evidence){throw 'invalid_retirement_root'}
   [void]$covered.Add((Full ([string]$r.path)))
  }
 }
 $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 $operations=[Collections.Generic.List[object]]::new()
 foreach($row in $config.roots){
  $p=Full ([string]$row.path)
  if(-not $seen.Add($p) -or -not $row.ownership_evidence){throw 'duplicate_or_unevidenced_root'}
  if(Inside $p $original){throw 'original_checkout_excluded'}
  $labels=@($sources.Keys|Where-Object{[IO.Path]::GetDirectoryName($p) -eq $sources[$_]})
  if($labels.Count -ne 1){throw 'exact_top_level_scope_required'}
  if($row.disposition -eq 'obsolete-amadeus-copy'){
   if(-not $covered.Contains($p) -or -not $candidates.ContainsKey($p) -or
    $candidates[$p].disposition -ne 'obsolete-amadeus-copy'){throw 'retirement_coverage_required'}
  }elseif($row.disposition -eq 'retain-ownership-unverified'){
   if(-not $uncertain.ContainsKey($p) -or $uncertain[$p].disposition -ne 'hold-ownership-unverified'){throw 'uncertain_classification_required'}
  }else{throw 'retention_disposition_required'}
  $parent=Join-Path (Join-Path $recovery 'retained-originals') $labels[0]
  $dest=Join-Path $parent ([IO.Path]::GetFileName($p))
  $operations.Add(@{source=$p;destination=$dest;parent=$parent;disposition=$row.disposition})
 }
 $stream=[IO.FileStream]::new([RetainNative]::Native($OutcomeLog),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
 $log=[IO.StreamWriter]::new($stream,[Text.UTF8Encoding]::new($false))
 $mode=if($Apply){'APPLY'}else{'PLAN'}
 $log.WriteLine((@{kind='start';mode=$mode;plan_sha256=(Hash $Plan);classification_sha256=$config.classification_sha256
  writers_stopped=$true;intact_retention_only=$true;started_at=[DateTimeOffset]::UtcNow.ToString('o')
  nested_links='Opaque; original absolute paths may be required for restoration.'}|ConvertTo-Json -Compress))
 $totals=@{planned=0;retained=0;absent=0;held=0;moved_unconfirmed=0}
 foreach($op in $operations){
  $handle=$null;$renamed=$false
  $out=@{source=$op.source;destination=$op.destination;disposition=$op.disposition}
  try{
   if(-not [RetainNative]::Exists($op.source)){
    if($op.disposition -eq 'retain-ownership-unverified'){throw 'unverified_source_absent_unresolved'}
    $out.action='absent';$out.reason='source_already_absent'
   }
   else{
    [RetainNative]::NoReparse($op.source);$before=[RetainNative]::Info($op.source)
    if($before.Device -ne [RetainNative]::Info($recovery).Device){throw 'same_volume_required'}
    $probe=$op.parent
    while(-not [RetainNative]::Exists($probe)){$probe=[IO.Path]::GetDirectoryName($probe)}
    [RetainNative]::NoReparse($probe)
    if([RetainNative]::Exists($op.destination)){throw 'destination_exists'}
    $out.before=@{device=$before.Device;inode=$before.Inode;attributes=$before.Attributes;reparse_tag=$before.Tag}
    if(-not $Apply){$out.action='planned';$out.reason='intact_same_volume_retention'}
    else{
     foreach($directory in @((Join-Path $recovery 'retained-originals'),$op.parent)){
      if(-not [RetainNative]::Exists($directory)){[void][IO.Directory]::CreateDirectory($directory)}
      [RetainNative]::NoReparse($directory)
     }
     $handle=[RetainNative]::Open($op.source,$true)
     if(-not (Same $before ([RetainNative]::Handle($handle)))){throw 'source_identity_changed'}
     [RetainNative]::NoReparse($op.source);[RetainNative]::NoReparse($op.parent)
     if([RetainNative]::Info($op.parent).Device -ne $before.Device){throw 'destination_volume_changed'}
     [RetainNative]::Rename($handle,$op.destination);$renamed=$true
     $after=[RetainNative]::Info($op.destination)
     if(-not (Same $before $after) -or [RetainNative]::Exists($op.source)){throw 'rename_readback_unconfirmed'}
     $out.after=@{device=$after.Device;inode=$after.Inode;attributes=$after.Attributes;reparse_tag=$after.Tag}
     $out.action='retained';$out.reason='same_object_renamed_intact'
    }
   }
  }catch{
   $out.action=if($renamed){'moved_unconfirmed'}else{'held'};$out.reason=Reason $_
  }finally{if($handle){$handle.Dispose()}}
  $totals[$out.action]++;$log.WriteLine(($out|ConvertTo-Json -Compress -Depth 5));$log.Flush()
 }
 $result=@{status=$(if($totals.held -or $totals.moved_unconfirmed){'HOLDS_REMAIN'}else{'PASS'});mode=$mode
  finished_at=[DateTimeOffset]::UtcNow.ToString('o');totals=$totals;outcome_log=$OutcomeLog;original_checkout_excluded=$true}
 $log.WriteLine(($result|ConvertTo-Json -Compress -Depth 5));$log.Flush()
 Write-Output ($result|ConvertTo-Json -Compress -Depth 5)
 if($totals.held -or $totals.moved_unconfirmed){exit 2};exit 0
}catch{
 $failure=@{status='FAIL';reason=(Reason $_);mode=$(if($Apply){'APPLY'}else{'PLAN'})}
 if($log){$log.WriteLine(($failure|ConvertTo-Json -Compress));$log.Flush()}
 Write-Output ($failure|ConvertTo-Json -Compress);exit 1
}finally{if($log){$log.Dispose()};foreach($locked in $locks){$locked.Dispose()}}
