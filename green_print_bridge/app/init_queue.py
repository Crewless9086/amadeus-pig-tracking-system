"""One-shot root initializer for the fixed commissioned CUPS queue."""
import ipaddress,json,re,sys
from pathlib import Path
from urllib.parse import urlparse

def fail(stage,reason):
    print(f"green_startup_failed stage={stage} reason={reason}",file=sys.stderr)
    raise SystemExit(1)

def main(options_path,queue_path,hosts_path="/etc/hosts"):
    try: options=json.loads(Path(options_path).read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError): fail("configuration","options_invalid")
    queue=str(options.get("cups_queue_id","")); uri=urlparse(str(options.get("printer_uri","")))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",queue): fail("configuration","queue_invalid")
    try: pin=ipaddress.ip_address(str(options.get("printer_endpoint_ip","")))
    except ValueError: fail("configuration","printer_pin_invalid")
    try: literal=ipaddress.ip_address(uri.hostname or "")
    except ValueError: literal=None
    expected_path=f"/printers/{queue}"
    endpoint_valid=(options.get("printer_transport_profile")=="local_ipp_fixed"
        and uri.scheme=="ipp" and literal==pin and pin.is_private
        and (uri.port or 631)==631 and uri.path==expected_path
        and not uri.username and not uri.password and not uri.query and not uri.fragment)
    if not endpoint_valid: fail("configuration","local_ipp_fixed_endpoint_invalid")
    try: Path(queue_path).write_text(f"""<Printer {queue}>
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
    except OSError: fail("queue_configuration","queue_write_failed")
    print(queue)

if __name__=="__main__": main(sys.argv[1],sys.argv[2])
