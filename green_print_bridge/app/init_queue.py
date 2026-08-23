"""One-shot root initializer for the fixed commissioned CUPS queue."""
import ipaddress,json,re,socket,sys
from pathlib import Path
from urllib.parse import urlparse
from service import printer_tls_preflight

HOSTNAME=re.compile(r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?")

def fail(stage,reason):
    print(f"green_startup_failed stage={stage} reason={reason}",file=sys.stderr)
    raise SystemExit(1)

def host_bindings(path,hostname):
    found=set()
    try: lines=path.read_text(encoding="ascii").splitlines()
    except (OSError,UnicodeError): fail("printer_binding","hosts_read_failed")
    for line in lines:
        fields=line.split("#",1)[0].split()
        if len(fields)>=2 and hostname.casefold() in {x.casefold() for x in fields[1:]}:
            try: found.add(ipaddress.ip_address(fields[0]))
            except ValueError: fail("printer_binding","hosts_binding_invalid")
    return found

def install_binding(path,hostname,pin):
    existing=host_bindings(path,hostname)
    if existing and existing!={pin}: fail("printer_binding","hosts_binding_conflict")
    if not existing:
        try:
            with path.open("a",encoding="ascii") as hosts: hosts.write(f"{pin} {hostname}\n")
        except OSError: fail("printer_binding","hosts_write_failed")
    try: answers={ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(hostname,None,type=socket.SOCK_STREAM)}
    except (OSError,ValueError,TypeError): fail("printer_binding","fixed_binding_unresolved")
    if answers!={pin}: fail("printer_binding","fixed_binding_mismatch")

def main(options_path,queue_path,hosts_path="/etc/hosts"):
    try: options=json.loads(Path(options_path).read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError): fail("configuration","options_invalid")
    queue=str(options.get("cups_queue_id","")); uri=urlparse(str(options.get("printer_uri","")))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",queue): fail("configuration","queue_invalid")
    try: pin=ipaddress.ip_address(str(options.get("printer_endpoint_ip","")))
    except ValueError: fail("configuration","printer_pin_invalid")
    try: literal=ipaddress.ip_address(uri.hostname or "")
    except ValueError: literal=None
    if not literal and not HOSTNAME.fullmatch(uri.hostname or ""): fail("configuration","printer_hostname_invalid")
    endpoint_valid=(options.get("printer_transport_profile")=="private_ipps" and uri.scheme=="ipps" and pin.is_private and not uri.username and not uri.password and not uri.query and not uri.fragment)
    if literal and literal!=pin: endpoint_valid=False
    if not endpoint_valid: fail("configuration","private_ipps_endpoint_invalid")
    try: printer_tls_preflight(uri.hostname,str(pin),uri.port or 631,"/homeassistant/private-ca.crt")
    except Exception: fail("printer_tls","identity_or_connection_failed")
    if not literal: install_binding(Path(hosts_path),uri.hostname,pin)
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
