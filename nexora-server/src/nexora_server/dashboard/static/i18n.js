// Dashboard languages. Keys are the English text; {name} marks a value filled in at run time.
// Arabic is shown right to left. A missing translation falls back to English
// (tests/test_dashboard.py checks that every string the dashboard uses has an Arabic one).

const AR = {
  "Nexora Voice Cloud": "نيكسورا للصوت السحابي",
  "Skip to content": "انتقل إلى المحتوى",
  "Main": "الرئيسية",
  "Language": "اللغة",
  "Overview": "نظرة عامة",
  "API keys": "مفاتيح الواجهة البرمجية",
  "Profiles": "ملفات الإعدادات",
  "Sessions": "الجلسات",
  "Team": "الفريق",
  "Billing": "الفوترة",
  "Audit log": "سجل التدقيق",
  "Organizations": "المؤسسات",
  "Organization": "المؤسسة",
  "Sign out": "تسجيل الخروج",
  "Sign in": "تسجيل الدخول",
  "Paste an API key with the {scope} scope. It is kept only in this browser tab.":
    "الصق مفتاح واجهة برمجية بصلاحية {scope}. يُحفظ في علامة التبويب هذه فقط.",
  "API key": "مفتاح الواجهة البرمجية",
  "Sign in with SSO": "تسجيل الدخول الموحّد (SSO)",
  "Loading...": "جارٍ التحميل...",
  "Choose an organization": "اختر مؤسسة",
  "Choose an organization at the top right.": "اختر مؤسسة من أعلى الصفحة.",
  "super-admin": "مشرف عام",
  "This key does not have the admin scope.": "هذا المفتاح لا يملك صلاحية admin.",
  "minutes this month": "دقيقة هذا الشهر",
  "of {quota} minute quota": "من حصة {quota} دقيقة",
  "none": "لا يوجد",
  "monthly quota": "الحصة الشهرية",
  "sessions, last 30 days": "جلسة في آخر 30 يومًا",
  "calls right now / allowed at once": "مكالمة الآن / المسموح في وقت واحد",
  "{used} of {quota} minutes used": "استُخدمت {used} من {quota} دقيقة",
  "Audio minutes per day (last 30 days, by the day each call ended)":
    "دقائق الصوت يوميًا (آخر 30 يومًا، حسب يوم انتهاء كل مكالمة)",
  "No sessions yet.": "لا توجد جلسات بعد.",
  "Relay allowlist": "قائمة الوجهات المسموحة للتمرير",
  "Empty: Relay mode is off for this organization.": "فارغة: وضع التمرير متوقف لهذه المؤسسة.",
  "Audio minutes per day": "دقائق الصوت يوميًا",
  "{days} days, {total} minutes in total; busiest day {date} with {max} minutes.":
    "{days} يومًا، {total} دقيقة إجمالًا؛ أكثر الأيام نشاطًا {date} بـ {max} دقيقة.",
  "{n} min": "{n} د",
  "{date}: {min} min, {n} sessions": "{date}: {min} د، {n} جلسة",
  "New key": "مفتاح جديد",
  "(no name)": "(بلا اسم)",
  "never": "أبدًا",
  "revoked": "مُلغى",
  "Revoke": "إلغاء المفتاح",
  "Revoke key {name}": "إلغاء المفتاح {name}",
  "Name": "الاسم",
  "Key": "المفتاح",
  "Scopes": "الصلاحيات",
  "Created": "تاريخ الإنشاء",
  "Last used": "آخر استخدام",
  "Actions": "الإجراءات",
  "New API key": "مفتاح واجهة برمجية جديد",
  "e.g. production agents": "مثال: وكلاء الإنتاج",
  "Cancel": "إلغاء",
  "Create": "إنشاء",
  "Copy your new key now": "انسخ مفتاحك الجديد الآن",
  "It will not be shown again. Store it in your secrets manager.":
    "لن يظهر مرة أخرى. احفظه في مدير الأسرار لديك.",
  "Copy": "نسخ",
  "Done": "تم",
  "Revoke {name}?": "إلغاء {name}؟",
  "Anything using this key stops working at once. This cannot be undone.":
    "سيتوقف كل ما يستخدم هذا المفتاح فورًا. لا يمكن التراجع عن ذلك.",
  "Noise removal": "إزالة الضوضاء",
  "Noise engine": "محرك إزالة الضوضاء",
  "Echo cancellation (speakerphone callers)": "إلغاء الصدى (للمتصلين عبر مكبر الصوت)",
  "Speech guard (never cut speech on phone lines)": "حماية الكلام (عدم قطع الكلام على خطوط الهاتف)",
  "Background talker gate, dB below the caller (empty: off)":
    "كتم المتحدثين في الخلفية، بالديسيبل تحت مستوى المتصل (فارغ: متوقف)",
  "Voice enhancement": "تحسين الصوت",
  "Automatic gain": "التحكم التلقائي في مستوى الصوت",
  "Smart Turn (learned end of turn)": "Smart Turn (تحديد نهاية الدور بالتعلم الآلي)",
  "Transcript cue (\"...to\", \"um\" wait longer)": "إشارة النص (الانتظار أطول بعد كلمات مثل \"إلى\" و\"اممم\")",
  "Silence before replying when the caller sounds finished (ms)":
    "الصمت قبل الرد عندما يبدو أن المتصل أنهى كلامه (مللي ثانية)",
  "Silence before replying when unfinished (ms)": "الصمت قبل الرد عندما لم ينتهِ الكلام (مللي ثانية)",
  "Silence before replying without a verdict (ms)": "الصمت قبل الرد دون حكم (مللي ثانية)",
  "Caller speech needed to interrupt the agent (ms)": "كلام المتصل اللازم لمقاطعة الوكيل (مللي ثانية)",
  "New profile": "ملف إعدادات جديد",
  "A profile is a named set of audio and turn-taking settings; clients pick one with ?profile=name.":
    "ملف الإعدادات مجموعة مسماة من إعدادات الصوت وتبادل الأدوار؛ يختار العميل أحدها بـ ?profile=name.",
  "Audio": "الصوت",
  "Turns": "الأدوار",
  "Updated": "آخر تحديث",
  "default": "افتراضي",
  "off": "متوقف",
  "Edit": "تعديل",
  "Delete": "حذف",
  "Edit {name}": "تعديل {name}",
  "Delete {name}": "حذف {name}",
  "No profiles yet: every session uses the built-in defaults.":
    "لا توجد ملفات إعدادات بعد: كل جلسة تستخدم الإعدادات المدمجة.",
  "(default)": "(افتراضي)",
  "Turn-taking": "تبادل الأدوار",
  "Other audio settings (JSON)": "إعدادات صوت أخرى (JSON)",
  "No turn events": "بدون أحداث الأدوار",
  "Other turn settings (JSON)": "إعدادات أدوار أخرى (JSON)",
  "Default profile": "ملف الإعدادات الافتراضي",
  "Save": "حفظ",
  "Invalid JSON: {msg}": "JSON غير صالح: {msg}",
  "Delete {name}?": "حذف {name}؟",
  "Clients that ask for this profile will be refused.": "سيُرفض العملاء الذين يطلبون ملف الإعدادات هذا.",
  "Recent sessions": "أحدث الجلسات",
  "Started": "البداية",
  "Mode": "الوضع",
  "Duration": "المدة",
  "Status": "الحالة",
  "SNR dB": "نسبة الإشارة للضوضاء (dB)",
  "Lost audio %": "الصوت المفقود ٪",
  "Clipped %": "الصوت المقصوص ٪",
  "Engine": "المحرك",
  "{n} s": "{n} ث",
  "ended": "انتهت",
  "failed": "فشلت",
  "active": "نشطة",
  "process": "معالجة",
  "relay": "تمرير",
  "Export CSV": "تصدير CSV",
  "Export JSON Lines": "تصدير JSON Lines",
  "export failed ({status})": "فشل التصدير ({status})",
  "name@company.com": "name@company.com",
  "Email": "البريد الإلكتروني",
  "Role": "الدور",
  "admin": "مشرف",
  "viewer": "مشاهد",
  "viewer (usage only)": "مشاهد (الاستخدام فقط)",
  "Add": "إضافة",
  "People listed here can sign in to this dashboard with your company's single sign-on.":
    "يمكن للأشخاص المدرجين هنا تسجيل الدخول إلى لوحة التحكم عبر الدخول الموحّد لشركتك.",
  "Single sign-on is not configured on this server; members are kept for when it is.":
    "الدخول الموحّد غير مُعدّ على هذا الخادم؛ يُحتفظ بالأعضاء إلى أن يُعدّ.",
  "Added": "تاريخ الإضافة",
  "Last sign-in": "آخر تسجيل دخول",
  "Remove": "إزالة",
  "Remove {email}": "إزالة {email}",
  "No members yet.": "لا يوجد أعضاء بعد.",
  "Remove {email}?": "إزالة {email}؟",
  "They are signed out at once.": "سيُسجَّل خروجهم فورًا.",
  "Audio is reported to billing each hour, in whole seconds, when calls end.":
    "يُبلَّغ عن الصوت للفوترة كل ساعة، بالثواني الكاملة، عند انتهاء المكالمات.",
  "minutes reported (listed hours)": "دقيقة مُبلَّغ عنها (الساعات المعروضة)",
  "hours waiting to retry": "ساعة بانتظار إعادة المحاولة",
  "Hour (UTC)": "الساعة (UTC)",
  "Recorded s": "المسجَّل (ث)",
  "Reported s": "المُبلَّغ (ث)",
  "Sent": "وقت الإرسال",
  "sent": "أُرسلت",
  "pending": "قيد الانتظار",
  "empty": "فارغة",
  "Nothing reported yet (billing is off, or no calls have ended).":
    "لا يوجد ما يُبلَّغ عنه بعد (الفوترة متوقفة، أو لم تنتهِ أي مكالمة).",
  "When": "الوقت",
  "Who": "المنفّذ",
  "Action": "الإجراء",
  "Details": "التفاصيل",
  "Super-admin only.": "للمشرف العام فقط.",
  "New organization": "مؤسسة جديدة",
  "ID": "المعرّف",
  "Active": "نشطة",
  "Concurrent": "المتزامنة",
  "Quota (min/month)": "الحصة (دقيقة/شهر)",
  "suspended": "موقوفة",
  "Open": "فتح",
  "Open {name}": "فتح {name}",
  "Concurrent sessions": "الجلسات المتزامنة",
  "Monthly minutes quota (empty: none)": "حصة الدقائق الشهرية (فارغ: بلا حد)",
  "Relay allowlist, one host per line": "الوجهات المسموحة للتمرير، وجهة في كل سطر",
};

const TABLES = { ar: AR };
export const LANGS = [
  ["en", "English"],
  ["ar", "العربية"],
];
const RTL = new Set(["ar"]);
const PREF = "nexora.dashboard.lang"; // set only when the user picks a language

function initial() {
  try {
    const saved = localStorage.getItem(PREF);
    if (saved && LANGS.some(([c]) => c === saved)) return saved;
  } catch {
    // storage blocked: fall back to the browser language
  }
  const nav = (typeof navigator !== "undefined" && navigator.language) || "en";
  return nav.toLowerCase().startsWith("ar") ? "ar" : "en";
}

export let lang = initial();

export function setLang(code, remember = true) {
  lang = LANGS.some(([c]) => c === code) ? code : "en";
  if (remember) {
    try {
      localStorage.setItem(PREF, lang);
    } catch {
      // the choice then lasts for this page only
    }
  }
  document.documentElement.lang = lang;
  document.documentElement.dir = RTL.has(lang) ? "rtl" : "ltr";
}

// numbers and dates for the language; Western digits, matching IDs, keys and code
export const locale = () => (lang === "ar" ? "ar-u-nu-latn" : "en");

// translate; {name} placeholders are filled from vars (values are plain text)
export function t(text, vars = {}) {
  const s = TABLES[lang]?.[text] ?? text;
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}

// the keys, for the test that every string has a translation
export const KEYS = Object.keys(AR);
