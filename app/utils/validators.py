import ipaddress


def is_valid_ip(ip: str) -> bool:
    if not ip:
        return False
    try:
        ipaddress.ip_address(ip.strip())
        return True
    except ValueError:
        return False


def is_valid_port(port: int) -> bool:
    return isinstance(port, int) and 1 <= port <= 65535
