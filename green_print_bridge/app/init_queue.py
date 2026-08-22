"""One-shot root initializer for the fixed commissioned CUPS queue."""
import ipaddress,json,re,socket,sys
from pathlib import Path
from urllib.parse import urlparse
from service import printer_tls_preflight

options=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
queue=str(options.get("cups_queue_id","")); uri=urlparse(str(options.get("printer_uri","")))
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",queue): raise SystemExit("invalid queue")
try: pin=ipaddress.ip_address(str(options.get("printer_endpoint_ip","")))
except ValueError: raise SystemExit("invalid commissioned printer endpoint pin")
try: literal=ipaddress.ip_address(uri.hostname or "")
except ValueError: literal=None
if literal:
    answers={literal}
else:
    if not re.fullmatch(r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?",uri.hostname or ""): raise SystemExit("invalid printer TLS hostname")
    try: answers={ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(uri.hostname,None,type=socket.SOCK_STREAM)}
    except (OSError,ValueError,TypeError): raise SystemExit("printer private DNS resolution failed")
if options.get("printer_transport_profile")!="private_ipps" or uri.scheme!="ipps" or not pin.is_private or any(not x.is_private for x in answers) or answers!={pin} or uri.username or uri.password or uri.query or uri.fragment:
    raise SystemExit("invalid private IPPS endpoint")
try: printer_tls_preflight(uri.hostname,str(pin),uri.port or 631,"/config/private-ca.crt")
except Exception as exc: raise SystemExit("printer TLS SAN or trust verification failed") from exc
if not literal:
    # Bind CUPS to the commissioned address while retaining the hostname as
    # the TLS certificate identity. Later DNS changes cannot retarget IPPS.
    with Path("/etc/hosts").open("a",encoding="ascii") as hosts: hosts.write(f"{pin} {uri.hostname}\n")
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
print(queue)
