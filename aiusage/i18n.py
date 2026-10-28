"""Minimal UI localization (English source strings, Turkish translation).

`tr(text)` returns the translation of an English string or template, or the text unchanged.
Templates use `str.format` fields, e.g. `tr("resets in {d}").format(d=...)`.
Provider messages are translated at display time, so providers and logs stay in English.
"""

from __future__ import annotations

import os
import re

SUPPORTED = ("en", "tr")
_lang = "en"

TR = {
    # states
    "OK": "Tamam",
    "Stale": "Eski",
    "Not installed": "Kurulu değil",
    "Not authenticated": "Oturum açılmamış",
    "Rate limited": "Hız sınırına takıldı",
    "Unavailable": "Kullanılamıyor",
    "Unsupported": "Desteklenmiyor",
    "Disabled": "Devre dışı",
    "Loading…": "Yükleniyor…",
    "Local only": "Yalnızca yerel",
    # periods / labels
    "Today": "Bugün",
    "5 h": "5 sa",
    "7 d": "7 g",
    "30 d": "30 g",
    "All": "Tümü",
    "Last 5 hours": "Son 5 saat",
    "Last 7 days": "Son 7 gün",
    "Last 30 days": "Son 30 gün",
    "All scanned": "Taranan tümü",
    "5-hour session": "5 saatlik oturum",
    "Weekly": "Haftalık",
    "Primary": "Birincil",
    "Secondary": "İkincil",
    "{n}-hour session": "{n} saatlik oturum",
    "{n}-minute": "{n} dakikalık",
    "{n}-day": "{n} günlük",
    # card
    "Account quota": "Hesap kotası",
    "Local activity · recorded tokens": "Yerel etkinlik · kayıtlı tokenlar",
    "Model": "Model",
    "Input": "Girdi",
    "Output": "Çıktı",
    "Cache r/w": "Önbellek o/y",
    "Total": "Toplam",
    "Not installed — no CLI or local history found on this computer":
        "Kurulu değil — bu bilgisayarda CLI veya yerel geçmiş bulunamadı",
    "Disabled in settings": "Ayarlarda devre dışı",
    "Stale (last updated {age}): {detail}": "Eski (son güncelleme {age}): {detail}",
    "Source: {source}": "Kaynak: {source}",
    " — may change without notice": " — haber verilmeden değişebilir",
    "Weekly share: ": "Haftalık pay: ",
    "Daily recorded tokens, last {n} days ({start} → today) · hover for values":
        "Günlük kayıtlı tokenlar, son {n} gün ({start} → bugün) · değerler için üzerine gelin",
    "Daily recorded tokens (local), last {n} days · peak {peak}":
        "Günlük kayıtlı tokenlar (yerel), son {n} gün · en yüksek {peak}",
    "{day}: {short} tokens ({full})": "{day}: {short} token ({full})",
    "{n} files": "{n} dosya",
    "exact counts from local records": "yerel kayıtlardan kesin sayılar",
    "estimated": "tahmini",
    "{label}: {n} responses": "{label}: {n} yanıt",
    "input {v}": "girdi {v}",
    "output {v} (reasoning {r})": "çıktı {v} (akıl yürütme {r})",
    "cache read {v}": "önbellek okuma {v}",
    "cache write {v}": "önbellek yazma {v}",
    "Recorded in local logs; not account quota.": "Yerel kayıtlardan; hesap kotası değildir.",
    "No recorded usage ({period})": "Kayıtlı kullanım yok ({period})",
    # format helpers
    "reset time unknown": "sıfırlanma zamanı bilinmiyor",
    "reset passed · awaiting refresh": "sıfırlanma geçti · yenileme bekleniyor",
    "resets in {d}": "{d} sonra sıfırlanır",
    "resets {when} ({d})": "{when} sıfırlanır ({d})",
    "never": "hiç",
    "just now": "az önce",
    "{d} ago": "{d} önce",
    "not updated yet": "henüz güncellenmedi",
    "updated {time} ({age})": "güncellendi {time} ({age})",
    " (stale)": " (eski)",
    "today {v} tok": "bugün {v} token",
    # window / menus
    "AI Usage": "AI Kullanımı",
    "Refresh now": "Şimdi yenile",
    "Expand / collapse details": "Ayrıntıları aç / kapat",
    "Settings": "Ayarlar",
    "Hide to tray": "Tepsiye gizle",
    "Period for the per-model breakdown": "Model bazlı döküm için dönem",
    "Breakdown:": "Döküm:",
    "refreshing…": "yenileniyor…",
    "Show / hide": "Göster / gizle",
    "Settings…": "Ayarlar…",
    "Quit": "Çık",
    "{name}: {label} at {pct}%": "{name}: {label} %{pct}",
    "Reported by the provider's account interface.": "Sağlayıcının hesap arayüzü tarafından bildirildi.",
    # settings dialog
    "AI Usage — Settings": "AI Kullanımı — Ayarlar",
    "General": "Genel",
    "Language": "Dil",
    "Local refresh every": "Yerel yenileme aralığı",
    "Quota refresh every": "Kota yenileme aralığı",
    "Query timeout": "Sorgu zaman aşımı",
    "Follow system": "Sistemi izle",
    "Light": "Açık",
    "Dark": "Koyu",
    "Theme": "Tema",
    "Background opacity": "Arka plan opaklığı",
    "Keep above other windows (compositor permitting)":
        "Diğer pencerelerin üstünde tut (pencere yöneticisi izin verirse)",
    "Closing hides to the tray": "Kapatınca tepsiye gizle",
    "Start at login": "Oturum açılınca başlat",
    "Off": "Kapalı",
    "Notify at quota": "Kota bildirimi eşiği",
    "Providers": "Sağlayıcılar",
    "Enabled": "Etkin",
    "Query account quota": "Hesap kotasını sorgula",
    "No documented quota source exists for Antigravity": "Antigravity için belgelenmiş bir kota kaynağı yok",
    "claude command": "claude komutu",
    "codex command": "codex komutu",
    "Quota checks start the provider's own CLI (no model request). The widget never reads or stores credentials.":
        "Kota sorguları sağlayıcının kendi CLI'ını çalıştırır (model isteği yapılmaz). "
        "Uygulama kimlik bilgilerini asla okumaz veya saklamaz.",
    "Changing the language takes effect after a restart.": "Dil değişikliği yeniden başlatınca uygulanır.",
    # provider / engine details
    "Cached result; refreshing": "Önbellekteki sonuç; yenileniyor",
    "Claude Code is not logged in": "Claude Code'da oturum açılmamış",
    "Codex is not logged in": "Codex'te oturum açılmamış",
    "`claude` CLI not found": "`claude` CLI bulunamadı",
    "`codex` CLI not found": "`codex` CLI bulunamadı",
    "API-key account: no ChatGPT plan limits (API billing not shown)":
        "API anahtarı hesabı: ChatGPT plan limiti yok (API faturalaması gösterilmez)",
    "No active limit windows reported": "Etkin limit penceresi bildirilmedi",
    "No Antigravity conversation folder found": "Antigravity konuşma klasörü bulunamadı",
    "No Claude Code history folder found": "Claude Code geçmiş klasörü bulunamadı",
    "No Codex session folder found": "Codex oturum klasörü bulunamadı",
    "No documented quota source for Antigravity": "Antigravity için belgelenmiş kota kaynağı yok",
    "No subscription limits for this account (API key or unsupported plan)":
        "Bu hesapta abonelik limiti yok (API anahtarı veya desteklenmeyen plan)",
    "No verified quota source": "Doğrulanmış kota kaynağı yok",
    "Quota checks disabled in settings": "Kota sorguları ayarlarda kapalı",
    "Usage response had no limit windows": "Kullanım yanıtında limit penceresi yok",
    "Malformed app-server response": "Geçersiz app-server yanıtı",
    "Malformed usage response": "Geçersiz kullanım yanıtı",
    "Not authenticated or login expired": "Oturum açılmamış veya süresi dolmuş",
    "Provider process closed its input": "Sağlayıcı süreci girdisini kapattı",
    "Provider process exited": "Sağlayıcı süreci sonlandı",
    "Provider query failed": "Sağlayıcı sorgusu başarısız",
    "Provider timed out": "Sağlayıcı zaman aşımına uğradı",
    "Rate limited by provider (HTTP 429)": "Sağlayıcı hız sınırı uyguladı (HTTP 429)",
    "This Claude Code version has no usage query": "Bu Claude Code sürümünde kullanım sorgusu yok",
    "Unexpected permission request from CLI": "CLI'dan beklenmeyen izin isteği",
    "claude CLI get_usage (experimental, undocumented)": "claude CLI get_usage (deneysel, belgelenmemiş)",
    "codex app-server account/rateLimits/read": "codex app-server account/rateLimits/read",
    "Chats": "Sohbetler",
    "Other": "Diğer",
}

# Messages with variable parts (provider details are plain English strings).
PATTERNS = [
    (re.compile(r"^Local collection failed \((\w+)\)$"), "Yerel toplama başarısız ({0})"),
    (re.compile(r"^Quota query failed \((\w+)\)$"), "Kota sorgusu başarısız ({0})"),
    (re.compile(r"^(\d+) database\(s\) could not be read$"), "{0} veritabanı okunamadı"),
]

TR_WEEKDAYS = {"Mon": "Pzt", "Tue": "Sal", "Wed": "Çar", "Thu": "Per", "Fri": "Cum", "Sat": "Cmt", "Sun": "Paz"}


def system_language() -> str:
    try:
        from PySide6.QtCore import QLocale
        name = QLocale.system().name()
    except ImportError:  # pragma: no cover - PySide6 is a hard dependency
        name = os.environ.get("LANG", "")
    return "tr" if name.lower().startswith("tr") else "en"


def set_language(code: str) -> str:
    global _lang
    _lang = system_language() if code == "system" else (code if code in SUPPORTED else "en")
    return _lang


def language() -> str:
    return _lang


def tr(text: str) -> str:
    if _lang != "tr" or not text:
        return text
    hit = TR.get(text)
    if hit is not None:
        return hit
    for rx, template in PATTERNS:
        m = rx.match(text)
        if m:
            return template.format(*m.groups())
    return text


def tr_label(label: str) -> str:
    """Translate quota labels like 'Weekly · Opus' or '3-hour session · Spark' part by part."""
    if _lang != "tr":
        return label
    out = []
    for part in label.split(" · "):
        m = re.fullmatch(r"(\d+)-(hour session|minute|day)", part)
        if m:
            key = {"hour session": "{n}-hour session", "minute": "{n}-minute", "day": "{n}-day"}[m.group(2)]
            out.append(tr(key).format(n=m.group(1)))
        else:
            out.append(tr(part))
    return " · ".join(out)


def weekday(abbr: str) -> str:
    return TR_WEEKDAYS.get(abbr, abbr) if _lang == "tr" else abbr
