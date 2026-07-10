import ipaddress
import re

def validate_public_host(host: str) -> str:
    """
    驗證傳入的 host 是否為合法的公開 IP (IPv4 或 IPv6) 或合法網域
    如果是私有 IP, Loopback 或無效格式則拋出 ValueError
    """
    host = host.strip().lower()
    
    if host in ["localhost", "127.0.0.1", "::1"]:
        raise ValueError("Host cannot be localhost or loopback address")
    
    try:
        ip = ipaddress.ip_address(host)
        
        if ip.is_private:
            raise ValueError("Host cannot be a private IP address")
        if ip.is_loopback:
            raise ValueError("Host cannot be a loopback address")
        return host
    except ValueError as e:
        if "Must be a public IP" in str(e) or "not a routable" in str(e):
            raise
        pass
    
    domain_regex = re.compile(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$")
    
    if domain_regex.match(host):
        return host

    raise ValueError("Host must be a valid public IP address or domain name")