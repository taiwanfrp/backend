import ipaddress
import re


def validate_host(host: str, allow_private: bool = False) -> str:
    """
    驗證傳入的 host 是否為合法的公開 IP (IPv4 或 IPv6) 或合法網域
    如果是私有 IP, Loopback 或無效格式則拋出 ValueError
    - allow_private: 預設為 False, 若為 True 則允許私有 IP 與 Loopback
    """
    host = host.strip().lower()

    if host == "localhost":
        if allow_private:
            return host
        raise ValueError("Host cannot be localhost or loopback address")

    try:
        ip = ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False

    if is_ip:
        if not allow_private:
            if ip.is_private:
                raise ValueError("Host cannot be a private IP address")
            if ip.is_loopback:
                raise ValueError("Host cannot be a loopback address")
        return host

    domain_regex = re.compile(
        r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
    )

    if domain_regex.match(host):
        return host

    if allow_private:
        raise ValueError("Host must be a valid IP address or domain name")
    else:
        raise ValueError("Host must be a valid public IP address or domain name")
