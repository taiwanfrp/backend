import pytest
from app.utils.validators import validate_host

PUBLIC_HOSTS = [
    "8.8.8.8",                  # 公開 IPv4
    "1.1.1.1",                  # 公開 IPv4
    "2606:4700:4700::1111",     # 公開 IPv6
    "google.com",               # 標準網域
    "node-01.taiwanfrp.com",    # 包含連字號的子網域
    "test.wtf",                 # 奇怪但格式合法的 TLD
    "123-abc.co.uk",            # 複合網域
]

PRIVATE_HOSTS = [
    "127.0.0.1",                # IPv4 Loopback
    "localhost",                # Localhost 字串
    "10.0.0.5",                 # Class A 私有 IP
    "172.16.1.1",               # Class B 私有 IP
    "192.168.1.100",            # Class C 私有 IP
    "::1",                      # IPv6 Loopback
    "fd00::1",                  # IPv6 Unique Local (私有)
]

INVALID_FORMAT_HOSTS = [
    "invalid_domain",           # 沒有點 (如純數字 IP 轉換)
    "3232235876",               # 十進位花式 IP
    "domain.c",                 # TLD 太短 (小於 2 碼)
    "-domain.com",              # 不能以連字號開頭
    "domain-.com",              # 不能以連字號結尾
    "123..com",                 # 連續的點
    "http://google.com",        # 帶有 schema
    "google.com/path",          # 帶有路徑
]

@pytest.mark.parametrize("host", PUBLIC_HOSTS)
def test_validate_public_host_valid(host):
    """
    測試公開 IP 與網域
    無論 allow_private 為 False 或 True 都應該成功
    """
    assert validate_host(host) == host.lower().strip()
    assert validate_host(host, allow_private=True) == host.lower().strip()

@pytest.mark.parametrize("host", PRIVATE_HOSTS)
def test_validate_host_private_rejected_by_default(host):
    """
    測試私有/本地 IP (拒絕)
    預設情況 (allow_private=False) 須拋出 ValueError
    """
    with pytest.raises(ValueError) as exec_info:
        validate_host(host)
    print(f"Correctly rejected private host: {host}, reason: {exec_info.value}")

@pytest.mark.parametrize("host", PRIVATE_HOSTS)
def test_validate_host_private_allowed(host):
    """
    測試私有/本地 IP (允許)
    當 allow_private=True 時必須成功
    """
    assert validate_host(host, allow_private=True) == host.lower().strip()

@pytest.mark.parametrize("host", INVALID_FORMAT_HOSTS)
@pytest.mark.parametrize("allow_private", [False, True])
def test_validate_host_invalid_format(host, allow_private):
    """
    測試格式錯誤字串
    利用多重 parametrize 測試 allow_private 為 True/False 兩種情況皆須拋錯
    """
    with pytest.raises(ValueError):
        validate_host(host, allow_private=allow_private)
    print(f"Correctly rejected invalid format: {host} (allow_private={allow_private})")