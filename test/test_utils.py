import pytest
from app.utils.validators import validate_public_host

VALID_HOSTS = [
    "8.8.8.8",                  # 公開 IPv4
    "1.1.1.1",                  # 公開 IPv4
    "2606:4700:4700::1111",     # 公開 IPv6
    "google.com",               # 標準網域
    "node-01.taiwanfrp.com",    # 包含連字號的子網域
    "test.wtf",                 # 奇怪但格式合法的 TLD
    "123-abc.co.uk",            # 複合網域
]

INVALID_HOSTS = [
    # 私有與本地 IP
    "127.0.0.1",                # IPv4 Loopback
    "localhost",                # Localhost 字串
    "10.0.0.5",                 # Class A 私有 IP
    "172.16.1.1",               # Class B 私有 IP
    "192.168.1.100",            # Class C 私有 IP
    "::1",                      # IPv6 Loopback
    "fd00::1",                  # IPv6 Unique Local (私有)
    
    # 格式錯誤或惡意字串
    "invalid_domain",           # 沒有點 (如純數字 IP 轉換)
    "3232235876",               # 十進位花式 IP
    "domain.c",                 # TLD 太短 (小於 2 碼)
    "-domain.com",              # 不能以連字號開頭
    "domain-.com",              # 不能以連字號結尾
    "123..com",                 # 連續的點
    "http://google.com",        # 帶有 schema
    "google.com/path",          # 帶有路徑
]

@pytest.mark.parametrize("host", VALID_HOSTS)
def test_validate_public_host_valid(host):
    """
    測試 validate_public_host 函數對合法公開 IP 與網域的驗證
    """
    assert validate_public_host(host) == host.lower().strip()

@pytest.mark.parametrize("host", INVALID_HOSTS)
def test_validate_public_host_invalid(host):
    """
    測試 validate_public_host 函數對非法 IP 與網域的驗證
    """
    with pytest.raises(ValueError) as exec_info:
        validate_public_host(host)
        
    print(f"Invalid host correctly raised ValueError: {host}, error message: {exec_info.value}")