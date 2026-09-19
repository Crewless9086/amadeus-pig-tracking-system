#requires -Version 7.0
<#
PLAN by default; -Apply retires only explicitly owned and independently preserved
Amadeus copies. No recursive deletion, moves, ACL changes or provider calls. Deletion binds
to the verified open Windows handle, never a subsequently resolved pathname.
Keep source writers stopped. Hold anything changed, unlisted or uncertain.
Windows does not atomically exclude creation of a new alternate data stream.
The explicit stopped-writer precondition and immediate stream recheck are
required; any observed writer/stream/drift stops the affected allowlisted root.
#>
[CmdletBinding()]
param(
 [Parameter(Mandatory)][string]$Archive,
 [Parameter(Mandatory)][string]$Allowlist,
 [Parameter(Mandatory)][string]$VerificationReceipt,
 [Parameter(Mandatory)][string]$RestoreReceipt,
 [Parameter(Mandatory)][string]$OutcomeLog,
 [string]$DesktopRebindReceipt,
 [string]$PythonExe = 'python',
 [switch]$Apply
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Windows is required.' }
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Numerics;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public sealed class RetireInfo {
 public string Device, Inode, Mtime; public long Size; public uint Attributes, Tag;
}
public static class RetireNative {
 [StructLayout(LayoutKind.Sequential)] struct Id {public ulong Volume, Low, High;}
 [StructLayout(LayoutKind.Sequential)] struct Basic {public long Creation, Access, Write, Change; public uint Attr;}
 [StructLayout(LayoutKind.Sequential)] struct Standard {public long Allocation, End; public uint Links; public byte Pending, Directory;}
 [StructLayout(LayoutKind.Sequential)] struct Tag {public uint Attr, Value;}
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Stream {
  public long Size; [MarshalAs(UnmanagedType.ByValTStr,SizeConst=296)] public string Name;
 }
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 static extern SafeFileHandle CreateFileW(string p,uint a,uint s,IntPtr sec,uint c,uint f,IntPtr t);
 [DllImport("kernel32.dll",SetLastError=true,EntryPoint="GetFileInformationByHandleEx")]
 static extern bool ReadId(SafeFileHandle h,int k,out Id v,uint n);
 [DllImport("kernel32.dll",SetLastError=true,EntryPoint="GetFileInformationByHandleEx")]
 static extern bool ReadBasic(SafeFileHandle h,int k,out Basic v,uint n);
 [DllImport("kernel32.dll",SetLastError=true,EntryPoint="GetFileInformationByHandleEx")]
 static extern bool ReadStandard(SafeFileHandle h,int k,out Standard v,uint n);
 [DllImport("kernel32.dll",SetLastError=true,EntryPoint="GetFileInformationByHandleEx")]
 static extern bool ReadTag(SafeFileHandle h,int k,out Tag v,uint n);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 static extern IntPtr FindFirstStreamW(string p,int level,out Stream v,uint flags);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
 static extern bool FindNextStreamW(IntPtr h,out Stream v);
 [DllImport("kernel32.dll")] static extern bool FindClose(IntPtr h);
 [StructLayout(LayoutKind.Sequential)] struct Disposition {public uint Flags;}
 [DllImport("kernel32.dll",SetLastError=true)]
 static extern bool SetFileInformationByHandle(SafeFileHandle h,int kind,ref Disposition value,uint size);
 public static SafeFileHandle OpenForDelete(string p) {
  // DELETE + GENERIC_READ, share READ only: other writers/renames are excluded.
  var h=CreateFileW(Native(p),0x80000000|0x00010000,1,IntPtr.Zero,3,0x02000000|0x00200000,IntPtr.Zero);
  if(h.IsInvalid){int error=Marshal.GetLastWin32Error();h.Dispose();throw new Win32Exception(error);}
  return h;
 }
 public static void DeleteVerifiedHandle(SafeFileHandle h,string exactPath) {
  var actual=Info(exactPath);var locked=Handle(h);
  if(actual.Device!=locked.Device||actual.Inode!=locked.Inode)throw new IOException("delete_identity_changed");
  if(Streams(exactPath))throw new IOException("alternate_stream_present");
  // FILE_DISPOSITION_FLAG_DELETE | IGNORE_READONLY_ATTRIBUTE. This does not
  // rewrite ACLs or recursively delete directory children. Nonempty dirs fail.
  var value=new Disposition {Flags=0x01|0x10};
  Check(SetFileInformationByHandle(h,21,ref value,(uint)Marshal.SizeOf<Disposition>()));
 }
 public static FileStream LockInput(string p) {
  return new FileStream(Native(p),FileMode.Open,FileAccess.Read,FileShare.Read);
 }

 public static string Native(string p) {
  if(p.StartsWith(@"\\?\")) return p;
  return p.StartsWith(@"\\") ? @"\\?\UNC\"+p.Substring(2) : @"\\?\"+p;
 }
 static void Check(bool ok) {if(!ok) throw new Win32Exception(Marshal.GetLastWin32Error());}
 public static RetireInfo Handle(SafeFileHandle h) {
  Id id;Basic b;Standard s;Tag t;
  Check(ReadId(h,18,out id,(uint)Marshal.SizeOf<Id>()));
  Check(ReadBasic(h,0,out b,(uint)Marshal.SizeOf<Basic>()));
  Check(ReadStandard(h,1,out s,(uint)Marshal.SizeOf<Standard>()));
  Check(ReadTag(h,9,out t,(uint)Marshal.SizeOf<Tag>()));
  return new RetireInfo {Device=id.Volume.ToString(),
   Inode=(((BigInteger)id.High<<64)|id.Low).ToString(),
   Mtime=(((BigInteger)b.Write-116444736000000000L)*100).ToString(),
   Size=s.End,Attributes=t.Attr,Tag=t.Value};
 }
 public static RetireInfo Info(string p) {
  using(var h=CreateFileW(Native(p),0x80,7,IntPtr.Zero,3,0x02000000|0x00200000,IntPtr.Zero)) {
   if(h.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error()); return Handle(h);
  }
 }
 public static bool Link(RetireInfo v) {return (v.Tag&0x20000000)!=0;}
 public static void NoLinks(string p) {
  var chain=new Stack<string>();string value=p;
  while(!String.IsNullOrEmpty(value)) {chain.Push(value);string parent=Path.GetDirectoryName(value);
   if(parent==value) break;value=parent;}
  while(chain.Count>0) if(Link(Info(chain.Pop()))) throw new IOException("link_ancestor");
 }
 public static bool Streams(string p) {
  Stream v;IntPtr h=FindFirstStreamW(Native(p),0,out v,0);
  if(h==new IntPtr(-1)) {int e=Marshal.GetLastWin32Error();if(e==38)return false;throw new Win32Exception(e);}
  try {do {if(v.Name!="::$DATA")return true;} while(FindNextStreamW(h,out v));
   int e=Marshal.GetLastWin32Error();if(e!=38)throw new Win32Exception(e);return false;
  } finally {FindClose(h);}
 }
 public static bool Missing(string p) {
  try {Info(p);return false;} catch(Win32Exception e) {if(e.NativeErrorCode==2||e.NativeErrorCode==3)return true;throw;}
 }
}
'@
function Full([string]$Value) {
 if(-not [IO.Path]::IsPathFullyQualified($Value) -or $Value.StartsWith('\\?\')) {throw 'absolute_path_required'}
 $p=[IO.Path]::GetFullPath($Value).TrimEnd('\')
 if($p.Length -le 2 -or $Value -match '[*?]' -or $Value.Substring(2).Contains(':') -or
    $p -cne $Value.TrimEnd('\')) {throw 'resolved_narrow_path_required'}
 return $p
}
function Inside([string]$Path,[string]$Root) {
 return $Path.Equals($Root,[StringComparison]::OrdinalIgnoreCase) -or
  $Path.StartsWith($Root+'\',[StringComparison]::OrdinalIgnoreCase)
}
function Parts([string]$Relative,[bool]$Empty=$false) {
 if($Relative -eq '' -and $Empty){return @()}
 if(-not $Relative -or $Relative.StartsWith('/') -or $Relative.Contains('\') -or
    $Relative.Contains(':') -or $Relative.Contains([char]0)){throw 'unsafe_relative_path'}
 $parts=$Relative.Split('/')
 foreach($part in $parts) {
  if(-not $part -or $part -in @('.','..') -or $part.EndsWith('.') -or $part.EndsWith(' ') -or
     $part.Split('.')[0] -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$'){throw 'unsafe_relative_path'}
 }
 return $parts
}
function Source($Row) {
 if(-not $script:Sources.ContainsKey([string]$Row.label)){throw 'unknown_source'}
 $base=$script:Sources[[string]$Row.label]
 $parts=@(Parts ([string]$Row.relative) ($Row.type -ne 'file'))
 $p=if($parts.Count){[IO.Path]::Combine($base,[string]::Join('\',$parts))}else{$base}
 if(-not (Inside $p $base)){throw 'source_escape'};return $p
}
function Json([string]$Path) {
 [RetireNative]::NoLinks($Path)
 return [IO.File]::ReadAllText([RetireNative]::Native($Path))|ConvertFrom-Json -AsHashtable
}
function Hash([string]$Path) {
 [RetireNative]::NoLinks($Path)
 $f=[IO.FileStream]::new([RetireNative]::Native($Path),[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 $h=[Security.Cryptography.SHA256]::Create()
 try{return [Convert]::ToHexString($h.ComputeHash($f)).ToLowerInvariant()}finally{$h.Dispose();$f.Dispose()}
}
function RootOf([string]$Path,$Set) {
 $p=$Path
 while($p -and $p.Length -gt 3){if($Set.Contains($p)){return $p};$p=[IO.Path]::GetDirectoryName($p)}
 return $null
}
function PrefixIn([string]$Path,$Set) {
 $p=$Path
 while($p -and $p.Length -gt 3){if($Set.Contains($p)){return $true};$p=[IO.Path]::GetDirectoryName($p)}
 return $false
}
function Identity($Info,$Metadata,[string]$Kind='file') {
 if($Info.Device -ne [string]$Metadata.device -or $Info.Inode -ne [string]$Metadata.inode -or
    $Info.Attributes -ne $Metadata.file_attributes -or $Info.Tag -ne $Metadata.reparse_tag){return $false}
 # No Python filename-derived executable bits or unstable directory allocation
 # size. Directory mtime is checked BEFORE this script starts removing children.
 if($Kind -ne 'directory-after' -and $Info.Mtime -ne [string]$Metadata.mtime_ns){return $false}
 if($Kind -eq 'file' -and $Info.Size -ne $Metadata.size){return $false}
 return $true
}
function SafeReason($Record) {
 $cause=$Record.Exception
 while($cause.InnerException){$cause=$cause.InnerException}
 $message=$cause.Message
 if($message -match '^[a-z_]+$'){return $message}
 return $cause.GetType().Name+':line_'+$Record.InvocationInfo.ScriptLineNumber
}
function Ancestors([string]$Path) {
 $p=[IO.Path]::GetDirectoryName($Path)
 while($p -and $p.Length -gt 3){
  if($script:Ancestry.ContainsKey($p)){
   if(-not (Identity ([RetireNative]::Info($p)) $script:Ancestry[$p] 'directory-after')){throw 'ancestor_identity_changed'}
  }
  $p=[IO.Path]::GetDirectoryName($p)
 }
}
function Outcome([string]$Path,[string]$Action,[string]$Reason) {
 $script:Totals[$Action]++
 $script:Log.WriteLine((@{path=$Path;action=$Action;reason=$Reason}|ConvertTo-Json -Compress))
 $script:Progress++
 if($script:Progress%2000 -eq 0){$script:Log.Flush();Write-Host (@{progress=$script:Totals}|ConvertTo-Json -Compress)}
}
function Normal([string]$Path) {
 if($Path.StartsWith('\\?\UNC\')){return '\\'+$Path.Substring(8)}
 if($Path.StartsWith('\\?\')){return $Path.Substring(4)};return $Path
}
$script:Log=$null
$inputLocks=[Collections.Generic.List[IDisposable]]::new()
try {
 $Archive=Full $Archive;$Allowlist=Full $Allowlist;$VerificationReceipt=Full $VerificationReceipt
 $RestoreReceipt=Full $RestoreReceipt;$OutcomeLog=Full $OutcomeLog
 # Keep authenticated bytes immutable until all operations and receipts finish.
 # FileShare.Read prevents both content writes and replacement/deletion.
 $immutable=@($Allowlist,$VerificationReceipt,$RestoreReceipt)
 foreach($name in @('summary.json','key.dpapi','manifest.jsonl','objects.zip')){$immutable+=Join-Path $Archive $name}
 if($DesktopRebindReceipt){$DesktopRebindReceipt=Full $DesktopRebindReceipt;$immutable+=$DesktopRebindReceipt}
 foreach($inputPath in $immutable){[RetireNative]::NoLinks($inputPath);$inputLocks.Add([RetireNative]::LockInput($inputPath))}

 $config=Json $Allowlist
 if($config.version -ne 1 -or -not $config.owner_authorization -or -not $config.roots -or
    $config.writers_stopped -ne $true){throw 'explicit_ownership_and_stopped_writers_required'}
 $canonical=Full ([string]$config.canonical_checkout);$original=Full ([string]$config.protected_original_checkout)
 [RetireNative]::NoLinks($canonical)
 $rebound=$false
 if($DesktopRebindReceipt){
  $binding=Json (Full $DesktopRebindReceipt)
  $rebound=$binding.version -eq 1 -and $binding.kind -eq 'codex-desktop-project-rebind' -and
   $binding.status -eq 'PASS' -and $binding.evidence -and $binding.observed_at -and
   (Full ([string]$binding.canonical_checkout)) -eq $canonical -and
   (Full ([string]$binding.previous_checkout)) -eq $original
  if(-not $rebound){throw 'desktop_rebind_mismatch'}
 }
 $utility=Join-Path $PSScriptRoot 'workspace_archive.py'
 $pythonCode=@'
import importlib.util,json,sys
try:
 s=importlib.util.spec_from_file_location("archive_read",sys.argv[1])
 m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 summary,_=m.load_archive(sys.argv[2]);print(json.dumps(summary))
except Exception as exc:
 print(json.dumps({"error":type(exc).__name__}));sys.exit(1)
'@
 $authenticated=& $PythonExe -B -c $pythonCode $utility $Archive
 if($LASTEXITCODE -ne 0){throw 'archive_authentication_failed'}
 $summary=$authenticated|ConvertFrom-Json -AsHashtable
 $verification=Json $VerificationReceipt;$restoration=Json $RestoreReceipt
 foreach($receipt in @($verification,$restoration)){
  if($receipt.archive_sha256 -ne $summary.archive_sha256 -or $receipt.manifest_sha256 -ne $summary.manifest_sha256 -or
     (Full ([string]$receipt.archive)) -ne $Archive){throw 'receipt_binding_mismatch'}
 }
 if($verification.verification -ne 'PASS' -or $verification.verified_objects -ne $summary.counts.unique_objects -or
    $verification.verified_bytes -ne $summary.counts.unique_bytes -or $verification.holds -ne $summary.counts.holds -or
    [DateTimeOffset]::Parse($verification.verified_at) -lt [DateTimeOffset]::Parse($summary.finished_at)){
  throw 'complete_verification_required'
 }
 if($restoration.restore -ne 'PASS' -or $restoration.originals_modified -ne $false -or $restoration.files -lt 1 -or
    @($restoration.selections).Count -ne $restoration.files -or
    [DateTimeOffset]::Parse($restoration.restored_at) -lt [DateTimeOffset]::Parse($summary.finished_at)){
  throw 'restore_proof_required'
 }
 $destination=Full ([string]$restoration.destination);[RetireNative]::NoLinks($destination)
 $script:Sources=[Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
 foreach($root in $summary.roots){$script:Sources.Add([string]$root.label,(Full ([string]$root.path)))}
 $selectedOnly=$summary.ContainsKey('scope') -and $summary.scope -eq 'selected_paths_only'
 $selectedRoots=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 if($selectedOnly){
  foreach($selection in $summary.selections){
   [void]$selectedRoots.Add((Source @{label=$selection.label;relative=$selection.relative;type='directory'}))
  }
  if(-not $selectedRoots.Count){throw 'selected_scope_missing'}
 }

 $allowed=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 foreach($row in ($config.roots|Sort-Object{([string]$_.path).Length})){
  $p=Full ([string]$row.path)
  if($row.disposition -ne 'obsolete-amadeus-copy' -or -not $row.ownership_evidence){throw 'root_ownership_required'}
  if(-not @($script:Sources.Values|Where-Object{$p -ne $_ -and (Inside $p $_)}).Count){throw 'broad_or_unarchived_root'}
  foreach($protected in @($canonical,$Archive,$destination)){
   if((Inside $p $protected) -or (Inside $protected $p)){throw 'protected_path_overlap'}
  }
  if(PrefixIn $p $allowed){throw 'root_overlap'}
  if(-not $allowed.Add($p)){throw 'duplicate_root'}
 }
 $allowAncestors=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 foreach($root in $allowed){
  $ancestor=[IO.Path]::GetDirectoryName($root)
  while($ancestor -and $ancestor.Length -gt 3){
   [void]$allowAncestors.Add($ancestor);$ancestor=[IO.Path]::GetDirectoryName($ancestor)
  }
 }
 foreach($source in $script:Sources.Values){
  if((Inside $OutcomeLog $source) -or (Inside $destination $source)){throw 'evidence_inside_originals'}
 }
 if(Inside $OutcomeLog $Archive){throw 'log_inside_archive'}
 [RetireNative]::NoLinks([IO.Path]::GetDirectoryName($OutcomeLog))
 $logFile=[IO.FileStream]::new([RetireNative]::Native($OutcomeLog),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
 $script:Log=[IO.StreamWriter]::new($logFile,[Text.UTF8Encoding]::new($false))
 $script:Totals=@{planned=0;removed=0;removal_pending=0;held=0;directory_planned=0;directory_removed=0;directory_removal_pending=0};$script:Progress=0
 $mode=if($Apply){'APPLY'}else{'PLAN'}
 $script:Log.WriteLine((@{kind='start';mode=$mode;started_at=[DateTimeOffset]::UtcNow.ToString('o')
  archive_sha256=$summary.archive_sha256;manifest_sha256=$summary.manifest_sha256
  allowlist_sha256=(Hash $Allowlist);desktop_rebound=[bool]$rebound;writers_stopped=$true
  concurrency_contract='static_sources; new concurrent ADS is not atomically excluded'}|ConvertTo-Json -Compress))
 $held=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 if(-not $rebound){[void]$held.Add($original)}
 if(-not $rebound -and @($allowed|Where-Object{(Inside $_ $original) -or (Inside $original $_)}).Count){Outcome $original 'held' 'desktop_rebind_required'}
 $retainedDirectories=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 $script:Ancestry=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::OrdinalIgnoreCase)
 $listed=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 $directories=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::OrdinalIgnoreCase)
 $children=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::OrdinalIgnoreCase)
 $rehearsals=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
 foreach($selected in $restoration.selections){
  [void](Parts ([string]$selected.relative));$key=[string]$selected.label+':'+[string]$selected.relative
  if($rehearsals.ContainsKey($key)){throw 'duplicate_restore_selection'};$rehearsals.Add($key,$null)
 }
 $manifest=Join-Path $Archive 'manifest.jsonl';$rows=0
 $reader=[IO.StreamReader]::new([RetireNative]::Native($manifest))
 try{
  while($null -ne ($line=$reader.ReadLine())){
   $row=$line|ConvertFrom-Json -AsHashtable;$rows++
   try{$p=Source $row}catch{if($row.type -ne 'hold'){throw};[void]$held.Add($script:Sources[[string]$row.label]);continue}
   $key=[string]$row.label+':'+[string]$row.relative
   if($selectedOnly -and $row.type -eq 'file' -and -not (PrefixIn $p $selectedRoots)){throw 'file_outside_selected_scope'}
   if($row.type -eq 'file' -and $rehearsals.ContainsKey($key)){$rehearsals[$key]=$row}
   if($row.type -eq 'directory'){$script:Ancestry.Add($p,$row.metadata)}
   if(-not (PrefixIn $p $allowed)){
    # A narrow file allowlist must not bypass a hold on its containing tree.
    if($row.type -eq 'hold' -and $allowAncestors.Contains($p)){
     if($row.reason -eq 'directory_changed_during_scan'){[void]$retainedDirectories.Add($p)}
     else{[void]$held.Add($p)}
     Outcome $p 'held' ('archive_ancestor_hold:'+ [string]$row.reason)
    }
    continue
   }
   [void]$listed.Add($p)
   $parent=[IO.Path]::GetDirectoryName($p)
   if(-not $children.ContainsKey($parent)){$children.Add($parent,[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase))}
   [void]$children[$parent].Add($p)
   if($row.type -eq 'hold'){
    if($row.reason -eq 'directory_changed_during_scan'){[void]$retainedDirectories.Add($p)}
    else{[void]$held.Add($p)}
    Outcome $p 'held' ('archive_hold:'+ [string]$row.reason)
   }
   elseif($row.type -eq 'directory'){$directories.Add($p,$row.metadata)}
   elseif($row.type -ne 'file'){throw 'unknown_manifest_type'}
  }
 }finally{$reader.Dispose()}
 if($rows -ne $summary.manifest_entries){throw 'manifest_row_count_mismatch'}
 foreach($selection in $rehearsals.Values){
  if($null -eq $selection){throw 'restore_selection_missing'}
  $relative=[string]$selection.label+'/'+[string]$selection.relative
  $restored=[IO.Path]::Combine($destination,$relative.Replace('/','\'))
  if(-not (Inside $restored $destination) -or (Hash $restored) -ne $selection.sha256 -or
     [RetireNative]::Info($restored).Size -ne $selection.metadata.size){throw 'restored_file_changed'}
 }
 foreach($root in $allowed){if(-not $listed.Contains($root)){throw 'allowlist_object_not_preserved'}}
 # Before ANY removal, check directory identity, mtime, attributes and exact
 # immediate listings. Full captured trees hold on changed listings; selected-
 # scope ancestors require captured-child membership and retain other siblings.
 foreach($p in ($directories.Keys|Sort-Object{$_.Length})){
  if(PrefixIn $p $held){continue}
  try{
   [RetireNative]::NoLinks($p)
   $partial=$selectedOnly -and -not (PrefixIn $p $selectedRoots)
   $identityKind=if($partial){'directory-after'}else{'directory-before'}
   if(-not (Identity ([RetireNative]::Info($p)) $directories[$p] $identityKind) -or [RetireNative]::Streams($p)){throw 'directory_drift'}
   $actual=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
   foreach($entry in [IO.Directory]::EnumerateFileSystemEntries([RetireNative]::Native($p))){[void]$actual.Add((Normal $entry))}
   $expected=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
   if($children.ContainsKey($p)){$expected=$children[$p]}
   if($partial){
    if(-not $actual.IsSupersetOf($expected)){throw 'selected_child_missing'}
   }elseif(-not $actual.SetEquals($expected)){throw 'directory_listing_changed'}
  }catch{[void]$held.Add($p);Outcome $p 'held' ('directory_preflight_failed:'+(SafeReason $_))}
 }
 $reader=[IO.StreamReader]::new([RetireNative]::Native($manifest))
 try{
  while($null -ne ($line=$reader.ReadLine())){
   $row=$line|ConvertFrom-Json -AsHashtable;if($row.type -ne 'file'){continue};$p=Source $row
   if(-not (PrefixIn $p $allowed)){continue}
   if(PrefixIn $p $held){Outcome $p 'held' 'preservation_or_desktop_hold';continue}
   $stream=$null;$algorithm=$null;$dispositionAccepted=$false
   try{
    [RetireNative]::NoLinks($p);Ancestors $p;$before=[RetireNative]::Info($p)
    if(($before.Attributes -band 16) -ne 0 -or -not (Identity $before $row.metadata) -or [RetireNative]::Streams($p)){throw 'file_metadata_or_stream_changed'}
    if($Apply){
     $deleteHandle=[RetireNative]::OpenForDelete($p)
     try{$stream=[IO.FileStream]::new($deleteHandle,[IO.FileAccess]::Read)}catch{$deleteHandle.Dispose();throw}
    }else{$stream=[RetireNative]::LockInput($p)}
    if(-not (Identity ([RetireNative]::Handle($stream.SafeFileHandle)) $row.metadata)){throw 'open_file_changed'}
    $algorithm=[Security.Cryptography.SHA256]::Create()
    $digest=[Convert]::ToHexString($algorithm.ComputeHash($stream)).ToLowerInvariant()
    if($digest -ne $row.sha256 -or -not (Identity ([RetireNative]::Handle($stream.SafeFileHandle)) $row.metadata)){throw 'file_content_changed'}
    [RetireNative]::NoLinks($p);Ancestors $p
    if(-not (Identity ([RetireNative]::Info($p)) $row.metadata) -or [RetireNative]::Streams($p)){throw 'file_changed_before_removal'}
    if($Apply){
     [RetireNative]::DeleteVerifiedHandle($stream.SafeFileHandle,$p)
     $dispositionAccepted=$true
     $stream.Dispose();$stream=$null
     if(-not [RetireNative]::Missing($p)){throw 'removal_not_confirmed'}
     Outcome $p 'removed' 'verified_preserved_file'
    }else{Outcome $p 'planned' 'verified_preserved_file'}
   }catch{
    if($dispositionAccepted){Outcome $p 'removal_pending' 'disposition_accepted_disappearance_unconfirmed'}
    else{Outcome $p 'held' ('current_check_failed:'+(SafeReason $_))}
    $affected=RootOf $p $allowed
    if($held.Add($affected)){Outcome $affected 'held' 'source_check_or_busy_handle_stopped_allowlisted_subtree'}
   }
   finally{if($algorithm){$algorithm.Dispose()};if($stream){$stream.Dispose()}}
  }
 }finally{$reader.Dispose()}
 foreach($p in ($directories.Keys|Sort-Object{$_.Length} -Descending)){
  if((PrefixIn $p $held) -or $retainedDirectories.Contains($p)){continue}
  if($selectedOnly -and -not (PrefixIn $p $selectedRoots)){
   Outcome $p 'held' 'partial_scope_ancestor_retained';continue
  }
  $directoryHandle=$null;$dispositionAccepted=$false
  try{
   [RetireNative]::NoLinks($p);Ancestors $p
   if(-not (Identity ([RetireNative]::Info($p)) $directories[$p] 'directory-after') -or [RetireNative]::Streams($p)){throw 'directory_changed'}
   if(-not $Apply){Outcome $p 'directory_planned' 'conditional_on_proven_empty_after_files';continue}
   $directoryHandle=[RetireNative]::OpenForDelete($p)
   if(-not (Identity ([RetireNative]::Handle($directoryHandle)) $directories[$p] 'directory-after')){throw 'opened_directory_changed'}
   $iterator=[IO.Directory]::EnumerateFileSystemEntries([RetireNative]::Native($p)).GetEnumerator()
   try{$empty=-not $iterator.MoveNext()}finally{$iterator.Dispose()}
   if(-not $empty){Outcome $p 'held' 'directory_not_empty';continue}
   if([RetireNative]::Streams($p)){throw 'directory_stream_changed'}
   [RetireNative]::DeleteVerifiedHandle($directoryHandle,$p)
   $dispositionAccepted=$true
   $directoryHandle.Dispose();$directoryHandle=$null
   if(-not [RetireNative]::Missing($p)){throw 'directory_removal_not_confirmed'}
   Outcome $p 'directory_removed' 'verified_empty_directory'
  }catch{
   if($dispositionAccepted){Outcome $p 'directory_removal_pending' 'disposition_accepted_disappearance_unconfirmed'}
   else{Outcome $p 'held' ('directory_final_check_failed:'+(SafeReason $_))}
   $affected=RootOf $p $allowed
   if($held.Add($affected)){Outcome $affected 'held' 'directory_check_or_busy_handle_stopped_allowlisted_subtree'}
  }
  finally{if($directoryHandle){$directoryHandle.Dispose()}}
 }
 $hasPending=$script:Totals.removal_pending -or $script:Totals.directory_removal_pending
 $result=@{status=$(if($hasPending){'DISPOSITIONS_PENDING'}elseif($script:Totals.held){'HOLDS_REMAIN'}else{'PASS'});mode=$mode
  finished_at=[DateTimeOffset]::UtcNow.ToString('o');totals=$script:Totals
  archive_sha256=$summary.archive_sha256;manifest_sha256=$summary.manifest_sha256
  outcome_log=$OutcomeLog;original_checkout_protected=(-not $rebound)}
 $script:Log.WriteLine(($result|ConvertTo-Json -Compress -Depth 5));$script:Log.Flush()
 Write-Output ($result|ConvertTo-Json -Compress -Depth 5)
 if($script:Totals.held -or $hasPending){exit 2};exit 0
}catch{
 $failure=@{status='FAIL';reason=(SafeReason $_);mode=$(if($Apply){'APPLY'}else{'PLAN'})}
 if($script:Log){$script:Log.WriteLine(($failure|ConvertTo-Json -Compress));$script:Log.Flush()}
 Write-Output ($failure|ConvertTo-Json -Compress);exit 1
}finally{
 if($script:Log){$script:Log.Dispose()}
 foreach($locked in $inputLocks){$locked.Dispose()}
}

