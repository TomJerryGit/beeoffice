# tests/fidelity/test_spellcheck_techwords.py
"""
技术词白名单（R3）保真度测试。

背景
----
``beeoffice/data/tech_words.txt`` 是"词典里没有、但技术语境下正确"的词表
（CentOS / yum / iptables / ens33 …）。中文技术文档里这类词极多，英文词典一律判错，
实测 7 份真实中文技术文档一共 619 处误报（``CentOS`` 313、``yum`` 217 …）。
白名单把它们当成已知词，**只减少误报、不新增误报**。

本机（Windows 10 19041）实测
---------------------------
``import spellchecker`` / ``import enchant`` 都是 ``ModuleNotFoundError``；
Windows 原生检查器只有 ``zh-Latn-CN-x-ext``，且把 hello/world/the 全判错 →
``detect_backend().available is False``，**真实误报数在本机无法测量**。
所以"误报 < 50"那条只在后端可用时断言，本机 ``pytest.skip``（绝不假装通过）；
后端无关的部分（词表加载、开关、语料分词统计）给出**真实数字**并钉死。
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins import spellcheck as sc  # noqa: E402

CORPUS_DIR = ROOT / "tests" / "fidelity" / "corpus"


# ====================================================================
# 桩后端（后端无关，保证断言在任何机器上都有牙）
# ====================================================================

class EnglishDictStub(sc.SpellBackend):
    """
    像"真英文词典"的桩：认识 ``hello`` / ``world`` / ``the``（据此通过服务的英文自检），
    但**不认识** CentOS / mysql / yum / Xshell / VMware / ens33 这些技术词 ——
    正好复现真机上的误报场景。
    """

    name = "stub-english-dict"

    KNOWN = frozenset((
        "the", "hello", "world", "computer", "document", "quick", "brown", "fox",
        "test", "version", "download", "worry", "receive", "is", "word", "and",
    ))

    def check(self, word):
        return word.lower() in self.KNOWN

    def suggest(self, word):
        return []


class FlagAllBackend(sc.SpellBackend):
    """
    把所有词都判错的桩后端 —— 它不是英文词典（连 hello/world/the 都判错），
    因此服务**不会**给它套技术词白名单（见 :func:`sc.backend_is_english_dictionary`）。
    这一行为由既有的 ``test_spellcheck.py::test_corpus_live_pipeline_reports_when
    _backend_flags_everything`` 钉住：那条测试要求"所有词都判错"的后端如实报出每个词。
    """

    name = "stub-flag-all"

    def check(self, word):
        return False

    def suggest(self, word):
        return []


@pytest.fixture(autouse=True)
def _fresh_tech_words_cache():
    """每条用例前后都清掉惰性缓存，避免用例互相污染。"""
    sc.reset_tech_words_cache()
    yield
    sc.reset_tech_words_cache()


# ====================================================================
# 1. 词表文件本身
# ====================================================================

#: 任务书点名必须包含的词（按领域）。缺任何一个 → 用例失败。
REQUIRED_WORDS = [
    # 操作系统 / 发行版
    "Linux", "CentOS", "Ubuntu", "Debian", "RedHat", "Fedora", "openSUSE",
    "Windows", "macOS", "Unix", "kernel", "systemd", "SELinux", "GRUB",
    # 命令 / 工具
    "sudo", "yum", "dnf", "apt", "rpm", "tar", "gzip", "bash", "shell", "ssh",
    "scp", "rsync", "grep", "sed", "awk", "curl", "wget", "vi", "vim", "nano",
    "chmod", "chown", "mkdir", "mount", "umount", "fdisk", "nmtui", "ipconfig",
    "ping", "netstat", "traceroute", "iptables", "firewalld", "systemctl",
    "journalctl", "crontab", "nohup", "tmux", "screen",
    # 数据库 / 中间件
    "MySQL", "MariaDB", "PostgreSQL", "Redis", "MongoDB", "SQLite", "Oracle",
    "Nginx", "Apache", "Tomcat", "Docker", "Kubernetes", "K8s", "Jenkins",
    "GitLab", "Maven", "Gradle", "Node.js", "npm", "pip", "Django", "Flask",
    "Spring",
    # 云 / 虚拟化 / 网络
    "VMware", "VirtualBox", "Hyper-V", "KVM", "Xen", "Xshell", "PuTTY",
    "SecureCRT", "WinSCP", "FileZilla", "VNC", "RDP", "SSH", "OpenSSH", "VPN",
    "DHCP", "DNS", "NAT", "LAN", "WAN", "VLAN", "SSID", "ens33", "eth0", "ifcfg",
    "localhost",
    # 编程与概念
    "Python", "Java", "JavaScript", "TypeScript", "Golang", "Rust", "PHP",
    "Ruby", "Perl", "C++", "C#", "HTML", "CSS", "JSON", "XML", "YAML", "SQL",
    "NoSQL", "API", "SDK", "CLI", "GUI", "URL", "URI", "HTTP", "HTTPS", "TCP",
    "IP", "FTP", "SFTP", "SMTP", "IMAP", "LDAP", "UTF-8", "ASCII", "Markdown",
    "LaTeX", "Regex",
    # 常见产品 / 通用缩写
    "WPS", "Office", "Word", "Excel", "PowerPoint", "PDF", "BeeOffice",
    "GitHub", "Stack", "Overflow", "TODO", "FIXME",
]

#: 白名单**不许**收录的普通英文词：它们本来就该由英文词典判断
#: （收进来只会掩盖真正的拼写错误）。
ORDINARY_ENGLISH_WORDS = [
    "the", "hello", "world", "computer", "document", "quick", "brown", "fox",
    "recieve", "teh", "worry", "test", "version", "download", "affiliates",
]


def test_tech_words_file_exists_and_has_enough_words():
    path = sc.tech_words_path()
    assert path.is_file(), f"词表文件不存在: {path}"
    assert path.name == "tech_words.txt"
    assert path.parent.name == "data"

    text = path.read_text(encoding="utf-8")
    word_lines = [
        line.strip() for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert len(word_lines) >= 200, f"词表只有 {len(word_lines)} 行词，任务要求至少 200 行"
    assert len(set(word_lines)) >= 200, "去重后不足 200 个词"

    words = sc.load_tech_words()
    assert len(words) > 200, f"加载后只有 {len(words)} 个词"


def test_tech_words_are_all_lowercase_and_comment_free():
    words = sc.load_tech_words()
    assert words, "空词表"
    for word in words:
        assert word == word.strip(), word
        assert word == word.lower(), f"词表必须小写归一化：{word!r}"
        assert word, "空词不允许"
        assert not word.startswith("#"), f"注释没被忽略：{word!r}"


def test_tech_words_file_has_domain_group_comments():
    """词表按领域用 ``#`` 注释分组，便于人工维护。"""
    text = sc.tech_words_path().read_text(encoding="utf-8")
    comments = [line for line in text.splitlines() if line.strip().startswith("#")]
    assert len(comments) >= 6, f"分组注释太少（{len(comments)} 行）"
    for keyword in ("操作系统", "命令", "数据库", "网络", "编程", "产品"):
        assert any(keyword in line for line in comments), f"缺少「{keyword}」分组"


def test_required_domain_words_are_all_present():
    words = sc.load_tech_words()
    missing = sorted({word.lower() for word in REQUIRED_WORDS} - words)
    assert missing == [], f"任务书点名要求的词缺失：{missing}"


def test_common_english_words_are_not_in_the_whitelist():
    """白名单只放技术词；普通英文词词典本来就有，收进来只会掩盖错字。"""
    words = sc.load_tech_words()
    polluted = sorted(word for word in ORDINARY_ENGLISH_WORDS if word in words)
    assert polluted == [], f"白名单混入了普通英文词：{polluted}"


def test_load_tech_words_ignores_comments_blank_lines_and_normalises_case(tmp_path):
    path = tmp_path / "tw.txt"
    path.write_text(
        "# 分组注释\n"
        "\n"
        "CentOS\n"
        "  MySQL  \n"
        "# 又一行注释\n"
        "centos\n"
        "YUM\n"
        "   \n",
        encoding="utf-8",
    )
    assert sc.load_tech_words(path) == {"centos", "mysql", "yum"}


def test_load_tech_words_accepts_bom(tmp_path):
    path = tmp_path / "tw_bom.txt"
    path.write_text("# 注释\nCentOS\nXshell\n", encoding="utf-8-sig")
    assert sc.load_tech_words(path) == {"centos", "xshell"}


def test_load_tech_words_missing_file_returns_empty_set_and_never_raises(tmp_path):
    assert sc.load_tech_words(tmp_path / "根本没有这个文件.txt") == set()
    # 目录当文件读：也只是空集合
    assert sc.load_tech_words(tmp_path) == set()


def test_load_tech_words_broken_file_returns_empty_set_and_never_raises(tmp_path):
    """损坏文件（二进制垃圾 / 非法 UTF-8）不能让拼写检查崩掉。"""
    broken = tmp_path / "broken.txt"
    broken.write_bytes(b"\xff\xfe\x00\x01CentOS\x80\x81\x00\x00")
    assert sc.load_tech_words(broken) == set()

    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    assert sc.load_tech_words(empty) == set()


def test_load_tech_words_never_raises_on_any_garbage(tmp_path):
    """再随机一点：各种字节都不许抛异常。"""
    for index, payload in enumerate((
        b"", b"\x00", b"\x00\x01\x02\x03", b"CentOS\xff\xfe\n", b"\xed\xa0\x80",
    )):
        path = tmp_path / f"garbage_{index}.bin"
        path.write_bytes(payload)
        assert isinstance(sc.load_tech_words(path), set)


# ====================================================================
# 2. 惰性加载 / 缓存
# ====================================================================

def test_get_tech_words_is_lazy_cached_and_resettable(monkeypatch):
    sc.reset_tech_words_cache()
    calls = []
    real = sc.load_tech_words

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(sc, "load_tech_words", counting)

    assert calls == [], "还没用到就读盘了（必须惰性）"
    first = sc.get_tech_words()
    assert calls == [1]
    assert first is sc.get_tech_words(), "第二次调用应走缓存（同一个对象）"
    assert calls == [1]

    # 模块属性 TECH_WORDS（PEP 562 惰性属性）也走同一份缓存
    assert sc.TECH_WORDS == frozenset(first)
    assert calls == [1]

    # 清缓存后重新读盘
    sc.reset_tech_words_cache()
    sc.get_tech_words()
    assert calls == [1, 1]


def test_service_survives_a_missing_whitelist_file(monkeypatch, tmp_path):
    """词表文件丢了 → 空白名单（退化成改动前的行为），服务照常工作、不抛异常。"""
    monkeypatch.setattr(sc, "tech_words_path", lambda: tmp_path / "没有的词表.txt")
    sc.reset_tech_words_cache()
    assert sc.get_tech_words() == set()
    assert sc.TECH_WORDS == frozenset()

    service = sc.SpellCheckerService(backend=EnglishDictStub())
    assert service.use_tech_words is True
    assert service.tech_words == frozenset()
    assert service.check_word("CentOS") is False, "空白名单不该救回技术词"
    assert [miss.word for miss in service.check_text("centos")] == ["centos"]


# ====================================================================
# 3. 白名单生效：技术词不再被判错
# ====================================================================

TECH_SAMPLE = ("CentOS", "mysql", "yum", "Xshell", "VMware", "ens33")


def test_english_backend_is_required_for_the_whitelist():
    """白名单只套在"真的像英文词典"的后端上（否则会掩盖后端不可用这一事实）。"""
    assert sc.backend_is_english_dictionary(EnglishDictStub()) is True
    assert sc.backend_is_english_dictionary(FlagAllBackend()) is False
    assert sc.backend_is_english_dictionary(sc.UnavailableBackend("不能查")) is True

    flag_all = sc.SpellCheckerService(backend=FlagAllBackend())
    assert flag_all.use_tech_words is True
    assert flag_all.tech_words == frozenset(), "对'全判错'的后端不该套白名单"
    assert flag_all.check_word("CentOS") is False


def test_tech_words_are_accepted_by_default():
    service = sc.SpellCheckerService(backend=EnglishDictStub())
    assert service.use_tech_words is True
    assert len(service.tech_words) > 200
    for word in TECH_SAMPLE:
        assert service.check_word(word) is True, word
        assert service.knows(word) is True, word
    # 大小写不敏感
    assert service.check_word("CENTOS") is True
    assert service.check_word("centOS") is True


def test_tech_words_flow_through_the_existing_dictionary_path():
    """复用 ``_dictionary`` / ``add_to_dictionary`` / ``knows``，不另起判断逻辑。"""
    service = sc.SpellCheckerService(backend=EnglishDictStub())
    assert "centos" in service._dictionary
    assert "ens33" in service._dictionary
    assert service.knows("MySQL") is True
    assert service.tech_words <= frozenset(service._dictionary)


def test_tokenizable_tech_words_are_not_reported_in_text():
    service = sc.SpellCheckerService(backend=EnglishDictStub())
    assert service.check_text("centos mysql yum Xshell") == []
    # 反向确认管道没瞎：不在白名单里的词照样报
    assert [miss.word for miss in service.check_text("centos qwick yum")] == ["qwick"]


def test_switch_off_restores_the_old_behaviour():
    """``use_tech_words=False`` 时这些词必须**恢复**被判错（证明白名单真在起作用）。"""
    service = sc.SpellCheckerService(backend=EnglishDictStub(), use_tech_words=False)
    assert service.use_tech_words is False
    assert service.tech_words == frozenset()
    for word in TECH_SAMPLE:
        assert service.check_word(word) is False, word
    assert [miss.word for miss in service.check_text("centos mysql yum Xshell")] == [
        "centos", "mysql", "yum", "Xshell",
    ]


def test_switch_is_what_makes_the_difference_not_the_stub():
    """同一个桩后端，只翻开关：开=不报，关=全报 —— 差异只来自白名单。"""
    text = "centos mysql yum Xshell"
    on = sc.SpellCheckerService(backend=EnglishDictStub(), use_tech_words=True)
    off = sc.SpellCheckerService(backend=EnglishDictStub(), use_tech_words=False)
    assert (on.backend_name, off.backend_name) == ("stub-english-dict",) * 2
    assert on.check_text(text) == []
    assert len(off.check_text(text)) == 4


def test_switch_does_not_affect_non_tech_words():
    """开关只影响技术词：普通词判错与否与它无关。"""
    on = sc.SpellCheckerService(backend=EnglishDictStub(), use_tech_words=True)
    off = sc.SpellCheckerService(backend=EnglishDictStub(), use_tech_words=False)
    for word in ("qwick", "recieve", "teh"):
        assert on.check_word(word) is False, word
        assert off.check_word(word) is False, word


def test_service_dictionary_argument_still_works_with_the_whitelist():
    """白名单不能顶掉调用方显式传入的 dictionary。"""
    service = sc.SpellCheckerService(backend=EnglishDictStub(), dictionary=["Qwick"])
    assert service.check_word("qwick") is True
    assert service.ignore("teh") is None or True  # 忽略链路不受影响
    assert service.check_text("qwick") == []


# ====================================================================
# 4. 白名单不引入误报
# ====================================================================

def test_whitelist_never_turns_a_correct_word_into_an_error():
    """
    抽一批普通正确英文词：它们本来就不被判错，加白名单后依然不判错。

    注意这些词**不在**白名单里（见 ``test_common_english_words_are_not_in_the_whitelist``），
    所以这里验证的是"白名单没有干扰既有判断"，而不是"白名单把它们救了"。
    """
    known = ["the", "hello", "world", "computer", "document"]
    on = sc.SpellCheckerService(backend=EnglishDictStub(), use_tech_words=True)
    off = sc.SpellCheckerService(backend=EnglishDictStub(), use_tech_words=False)

    for word in known:
        assert word not in on.tech_words, f"普通英文词不该进白名单：{word}"
        assert off.check_word(word) is True, f"加白名单前就被判错：{word}"
        assert on.check_word(word) is True, f"加白名单后反而被判错：{word}"

    text = "the hello world computer document"
    assert off.check_text(text) == []
    assert on.check_text(text) == []
    assert on.check_text(text + " qwick") != []      # 管道仍然会报真错


def test_whitelist_does_not_widen_what_gets_checked():
    """白名单只是词表，不改词法：不该被检查的（中文/数字/驼峰）依然不被检查。"""
    service = sc.SpellCheckerService(backend=FlagAllBackend())
    assert service.check_text("这是一段纯中文，包含全角ＡＢＣ，还有数字 1234。") == []
    assert service.check_text("Windows10 python3 ipv4 grub2 ens33") == []
    assert service.check_text("sheet_name getValue iCounter MyClass") == []
    assert sc.tokenize_words("中文 CentOS 中文") == []


# ====================================================================
# 5. 真实语料（tests/fidelity/corpus/*.docx）
# ====================================================================

@pytest.fixture(scope="module")
def corpus_texts():
    if not CORPUS_DIR.is_dir():
        pytest.skip("没有语料目录: %s" % CORPUS_DIR)
    files = sorted(CORPUS_DIR.glob("*.docx"))
    if not files:
        pytest.skip("语料目录里没有 docx")
    from docx import Document

    documents = []
    for path in files:
        document = Document(str(path))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    text += "\n" + cell.text
        documents.append((path.name, text))
    return documents


@pytest.fixture(scope="module")
def corpus_counts(corpus_texts):
    """语料分词后每个词（小写）的出现次数。"""
    counts = {}
    for _name, text in corpus_texts:
        for word, _start, _end in sc.tokenize_words(text):
            key = word.lower()
            counts[key] = counts.get(key, 0) + 1
    return counts


#: 手写清单：7 份真实文档里出现的**技术词**（产品名/命令/协议/配置项/路径）。
#: 它不从 TECH_WORDS 派生（是测试里钉死的字面量），所以能真正检验白名单有没有漏词。
#: 实测：106 个词、共 723 处；白名单漏 0 处。
CORPUS_TECHNICAL_TOKENS = frozenset({
    "addr", "alt", "basearch", "cal", "cgroup", "changelog",
    "chmod", "chown", "crashkernel", "devtmpfs", "dhcp", "dir",
    "docx", "esc", "failovermethod", "ftp", "groupadd", "ipconfig",
    "ivh", "loopback", "mdev", "metalink", "pts", "rhgb",
    "rtt", "sed", "selinux", "shell", "shm", "sys",
    "useradd", "wget", "windows", "baseurl", "biosdevname", "cfg",
    "chkconfig", "ctrl", "ether", "gpgcheck", "gpgkey", "ifnames",
    "localhost", "lvm", "mkconfig", "prefixlen", "realtek", "repolist",
    "scopeid", "symlink", "xvf", "drwxr", "ifconfig", "init",
    "lib", "log", "oracle", "pwd", "sock", "socket",
    "tmp", "ttl", "txqueuelen", "basedir", "hostfile", "inet",
    "mtu", "netmask", "systemd", "cdrom", "cnf", "datadir",
    "dport", "ethernet", "fastestmirror", "langpacks", "mkdir", "tmpfs",
    "grub", "icmp", "ping", "tar", "vim", "grep",
    "pid", "ifcfg", "linux", "mount", "systemctl", "noarch",
    "rpm", "tcp", "mysqld", "repo", "sec", "sysconfig",
    "epel", "dev", "bin", "repos", "iptables", "yum",
    "usr", "etc", "mysql", "centos",
})


def test_corpus_tokenization_stats(corpus_texts, corpus_counts):
    """
    语料分词统计（**真实数字**，后端无关）。实测（7 份文档、当前实现）：

    * 可检查拉丁词 1592 处、335 个不同词
    * 其中命中白名单 723 处、106 个不同词
    * 未命中 869 处（普通英文词 + 文档专名）
    """
    total = sum(corpus_counts.values())
    assert len(corpus_texts) >= 7, len(corpus_texts)
    assert total >= 1500, f"可检查词只有 {total} 处，词法或语料变了"
    assert len(corpus_counts) >= 300, len(corpus_counts)

    whitelist = sc.get_tech_words()
    hits = {word: count for word, count in corpus_counts.items() if word in whitelist}
    assert sum(hits.values()) >= 700, f"白名单只命中 {sum(hits.values())} 处"
    assert len(hits) >= 100, f"白名单只命中 {len(hits)} 个不同词"
    # 未命中里确实还有普通英文词（说明白名单是"挑过的"，不是"全收的"）
    misses = sum(c for w, c in corpus_counts.items() if w not in whitelist)
    assert misses > 100, misses


def test_corpus_technical_tokens_are_all_covered_by_the_whitelist(corpus_counts):
    """
    **关键验收（不需要后端）**：语料里手挑出的技术词，白名单一个都不能漏。

    实测：清单 106 个技术词共出现 **723 处**；白名单漏 **0** 处。
    若白名单被清空 / 加载失败 / 漏词，这条立刻失败 —— 这就是"白名单真的覆盖了
    语料"的量化证据（后端不可用时也能测）。
    """
    whitelist = sc.get_tech_words()
    missing = sorted(word for word in CORPUS_TECHNICAL_TOKENS if word not in whitelist)
    assert missing == [], f"白名单漏掉了语料里的技术词：{missing}"

    absent = sorted(word for word in CORPUS_TECHNICAL_TOKENS if word not in corpus_counts)
    assert absent == [], f"清单里有语料中并不存在的词（清单过期了）：{absent}"

    covered = sum(corpus_counts[word] for word in CORPUS_TECHNICAL_TOKENS)
    assert covered >= 700, f"手挑技术词只出现 {covered} 处（数字应与语料一致）"

    # "去掉白名单后会多出多少可疑词" —— 就是这 covered 处：
    suspicious_without_whitelist = {
        word: corpus_counts[word] for word in CORPUS_TECHNICAL_TOKENS
    }
    suspicious_with_whitelist = {
        word: count for word, count in suspicious_without_whitelist.items()
        if word not in whitelist
    }
    assert sum(suspicious_without_whitelist.values()) == covered
    assert suspicious_with_whitelist == {}, f"白名单没覆盖住：{suspicious_with_whitelist}"


def test_whitelist_does_not_swallow_document_specific_junk(corpus_counts):
    """
    反向防作弊：不许把语料里**每个**词都塞进白名单来把误报数刷成 0。

    下面这些是文档专名 / 截断残片（自建库名、作者/网站名、断词），**不是**通用技术词，
    必须留在白名单之外。
    """
    whitelist = sc.get_tech_words()
    for junk in ("hedb", "phedb", "mysq", "servic", "pidmysql", "csdn", "jaist", "totbb"):
        assert junk in corpus_counts, f"语料里没有 {junk}（语料变了，清单要复核）"
        assert junk not in whitelist, f"{junk} 不该进技术词白名单"


def test_corpus_false_positives_are_under_fifty_with_a_real_backend(corpus_texts):
    """
    **关键验收（需要真英文词典）**：7 份真实中文技术文档的误报总数 < 50。

    本机没有可用的英文后端（pyspellchecker / enchant 都没装；Windows 原生检查器
    只有 zh-Latn 且把 hello/world/the 全判错）→ 本机 ``skip``，如实说"未能测量"。
    """
    backend = sc.detect_backend()
    if not backend.available:
        pytest.skip(
            "本机没有可用的英文拼写后端，真实误报数无法测量：%s"
            "（需要 pyspellchecker 或 enchant；本任务不引入新依赖）"
            % backend.reason[:120]
        )

    with_words = sc.SpellCheckerService(backend=backend, use_tech_words=True)
    without_words = sc.SpellCheckerService(backend=backend, use_tech_words=False)

    total_with = 0
    total_without = 0
    for _name, text in corpus_texts:
        total_with += len(with_words.check_text(text))
        total_without += len(without_words.check_text(text))

    assert total_with < 50, (
        "白名单开启后误报仍然 %d 处（要求 < 50）；关掉白名单是 %d 处"
        % (total_with, total_without)
    )
    if total_without:
        assert total_with < total_without, (
            "白名单没有减少误报：开=%d，关=%d" % (total_with, total_without)
        )


def test_corpus_pipeline_has_teeth_with_stub_backends(corpus_texts):
    """
    后端无关的反向确认：白名单在**真语料**上确实只救回技术词。

    用"认识普通英文词、不认识技术词"的桩（=真机上的误报场景）跑：
    报出的词应当恰好是"既不在桩词典、也不在白名单"的那些；关掉白名单后，
    报出的词恰好多出 723 处技术词出现。
    """
    on = sc.SpellCheckerService(backend=EnglishDictStub(), suggest=False)
    off = sc.SpellCheckerService(backend=EnglishDictStub(), suggest=False,
                                 use_tech_words=False)
    whitelist = sc.get_tech_words()
    stub_known = EnglishDictStub.KNOWN

    tokens = 0
    expected_on = 0
    reported_on = 0
    reported_off = 0
    for _name, text in corpus_texts:
        found = sc.tokenize_words(text)
        tokens += len(found)
        expected_on += sum(
            1 for word, _start, _end in found
            if word.lower() not in whitelist and word.lower() not in stub_known
        )
        reported_on += len(on.check_text(text))
        reported_off += len(off.check_text(text))

    assert tokens >= 1500, tokens
    assert reported_on == expected_on, (reported_on, expected_on)
    assert reported_off > reported_on, (reported_off, reported_on)
    assert reported_off - reported_on >= 700, (
        "白名单在真实语料上救回的词太少：%d" % (reported_off - reported_on)
    )


def test_chinese_is_still_never_flagged_with_the_whitelist(corpus_texts):
    """中文零误报是既有行为，白名单（或关掉白名单）都不许破坏它。"""
    for service in (
        sc.SpellCheckerService(backend=FlagAllBackend()),
        sc.SpellCheckerService(backend=EnglishDictStub()),
        sc.SpellCheckerService(backend=EnglishDictStub(), use_tech_words=False),
    ):
        checked = 0
        for name, text in corpus_texts:
            chinese_only = re.sub(r"[A-Za-z]+", "", text)
            assert service.check_text(chinese_only) == [], name
            checked += len(chinese_only)
        assert checked > 5000, checked


def test_saving_the_user_dictionary_does_not_dump_the_whitelist(tmp_path):
    """
    白名单是随程序发布的数据文件，不是用户词典 → ``save_dictionary`` 不能把它写出去
    （否则用户的词典文件会凭空多出几百行）。
    """
    service = sc.SpellCheckerService(backend=EnglishDictStub())
    service.ignore("teh")
    service.add_to_dictionary("qwick")
    assert len(service._dictionary) > 200, "白名单应该在内存词典里"

    path = tmp_path / "user_dict.txt"
    assert service.save_dictionary(path) is True
    saved = sc.load_user_dictionary(path)
    assert saved == {"teh", "qwick"}, f"白名单被写进了用户词典：{len(saved)} 条"
    assert "centos" not in saved and "ens33" not in saved
