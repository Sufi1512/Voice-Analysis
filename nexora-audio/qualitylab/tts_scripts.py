"""Scripted caller turns for the synthetic turn-taking set (``turns_tts``).

Each mid-sentence entry is (words before the pause, words after). The first part can never
be a whole sentence on its own (labelled by grammar, written before any measurement). About
half end on a word in ``nexora_audio.streaming.text_cues`` and half do not ("...is",
"...with", "...when"), so the text cue is not handed an easy test. Sentence entries are two
complete sentences with the pause between them.

Pure Python: imported both by the generator (separate TTS environment) and by the corpus.
"""

from __future__ import annotations

MID: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("I want to book a flight to", "Riyadh on Thursday morning."),
        ("Can you check the status of", "my order from last week?"),
        ("I called yesterday because", "my internet keeps dropping."),
        ("My account number is", "four five six seven eight."),
        ("I'd like to speak with", "someone in billing, please."),
        ("The problem started when", "I updated the app."),
        ("We need a table for", "six people at eight tonight."),
        ("I paid the bill but", "it still shows as unpaid."),
        ("Could you send the receipt to", "my work email instead?"),
        ("It's the blue one with", "the white stripes on the side."),
        ("So what I really need is", "a refund for the second item."),
        ("I was charged twice and", "nobody has called me back."),
    ],
    "ar": [
        ("أريد أن أحجز رحلة إلى", "الرياض يوم الخميس."),
        ("ممكن تساعدني في", "تغيير موعد الحجز؟"),
        ("اتصلت أمس لأن", "الإنترنت ينقطع كل ساعة."),
        ("عندي مشكلة مع", "الفاتورة الأخيرة."),
        ("أبغى أكلم الموظف اللي", "ساعدني المرة الماضية."),
        ("رقم الحساب هو", "أربعة خمسة ستة سبعة."),
        ("الطلب وصل لكن", "كان ناقص قطعة واحدة."),
        ("الموعد اللي حجزته كان", "يوم الأحد الساعة عشرة."),
        ("دفعت المبلغ و", "ما زال يظهر غير مدفوع."),
        ("أرسلت لكم رسالة على", "البريد الإلكتروني أمس."),
        ("المشكلة بدأت لما", "حدثت التطبيق."),
        ("أبي أعرف ليش", "الخدمة متوقفة من يومين."),
    ],
}

SENTENCE: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("I want to cancel my order.", "It hasn't shipped yet."),
        ("My name is Sara Ahmed.", "I'm calling about my booking."),
        ("The delivery was late again.", "This is the third time."),
        ("I already tried restarting it.", "The light is still red."),
    ],
    "ar": [
        ("أريد إلغاء الطلب.", "لم يتم شحنه بعد."),
        ("اسمي سارة أحمد.", "أتصل بخصوص الحجز."),
        ("التوصيل تأخر مرة ثانية.", "هذه المرة الثالثة."),
        ("جربت إعادة التشغيل.", "الضوء ما زال أحمر."),
    ],
}

# How the pause is made (the voice cannot hesitate by itself):
#   comma - the whole sentence is synthesised with a comma at the pause, so the voice keeps a
#           "going on" tone there, and the short comma gap is stretched to the pause length
#   split - the two parts are synthesised separately and joined, so the first part ends with
#           a falling, finished-sounding tone: a caller trailing off mid-sentence
VARIANTS = ("comma", "split")
