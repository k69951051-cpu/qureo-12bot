"""
واجهة Qureo تجريبية (غير متصلة بالمنصة).
لا تضف endpoints أو headers أو cookies مستنتجة من Network Capture.
عند استلام توثيق API رسمي، نفّذ الدوال هنا باستخدام OAuth/token رسمي.
"""

class QureoAdapter:
    def __init__(self, access_token=None):
        self.access_token = access_token

    def get_current_student(self):
        raise NotImplementedError(
            "يلزم API رسمي موثق وصلاحية وصول معتمدة."
        )

    def get_lessons(self):
        raise NotImplementedError(
            "يلزم API رسمي موثق وصلاحية وصول معتمدة."
        )

    def submit_answer(self, activity_id, answer):
        raise NotImplementedError(
            "إرسال الإجابات للمنصة غير مفعّل قبل توفير واجهة رسمية."
        )
