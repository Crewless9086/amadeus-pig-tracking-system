"""One-shot root initializer for the fixed commissioned CUPS queue."""
import ipaddress,json,re,sys
from pathlib import Path
from urllib.parse import urlparse

options=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
queue=str(options.get("cups_queue_id","")); uri=urlparse(str(options.get("printer_uri","")))
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",queue): raise SystemExit("invalid queue")
try: address=ipaddress.ip_address(uri.hostname or "")
except ValueError: raise SystemExit("printer endpoint must be an IP literal with matching certificate SAN")
if uri.scheme!="ipps" or not address.is_private or uri.username or uri.password or uri.query or uri.fragment:
    raise SystemExit("invalid private IPPS endpoint")
Path(sys.argv[2]).write_text(f"""<Printer {queue}>
PrinterId 1
Info Commissioned weekly A4 queue
DeviceURI {uri.geturl()}
State Idle
Accepting Yes
Shared No
Option media A4
Option sides one-sided
</Printer>
""",encoding="utf-8")
