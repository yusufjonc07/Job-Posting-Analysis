"""Job-offer classifier: every case below was a real message (or close to one) seen in the data."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.job_filter import KINDS, classify_post, is_job_post

CASES = {
    # job offers, in Uzbek (Latin and Cyrillic, with typing shortcuts), Russian and Korean
    "Иш бор": "job_offer",
    "Srocni ikki kiwiga iw bor srocni moshinali": "job_offer",
    "MALAKALI KATTA OSHPAZ KERAK! Oylik 3.000.000": "job_offer",
    "Dushan kunga 10 kishga ish bor tekpeda Pul ertasiga beriladi 01067267741": "job_offer",
    "Xozirga 2kishi kerak 1tasiga moshina bulishi kerak 60.000won beradi har bir bolaga": "job_offer",
    "ASSALOM ALAYKUM DEJON CJ vs OKCHEON CJ DOIMIYGA 10KISHI KERAK ISH HAFTADA 7kun buladi": "job_offer",
    "Assalomu alaykum ertaga bir kishiga samushil ishi bor shu manzilda 수레실길221-5": "job_offer",
    "Seshanba 25ta Manzil: 이천시 대월면 초지리57 20:00dan boshlanadi 6:00gacha 19:00gacha yetib kelish kerak": "job_offer",
    "20 TA ERKAK KISHIGA 20 ta AYOL QIZLAR gaish ISH TURI koja tortish 8dan 19.30 gacha": "job_offer",
    "JINCHEON TEKPE 6 kishiga joy qoldi 12 soat 150ming 17:30 dan 5:30 gacha chanop 13000won Manzil 충북 진천": "job_offer",
    "Zavodga 3 kishiga ish bor. Oylik 2.800.000 won. Uy beriladi, benzin puli beriladi": "job_offer",
    "Требуется 30мужчина на почту понедельника по пятницу на разгрузку инчен обедом кормят": "job_offer",
    "Ищу девушек для работы на неполный рабочий день в Гансо-гу. 50 000 вон в час.": "job_offer",
    "Assalom alekum gruppadagilar koreada servis E9-5 atkasda bulsela lich yozila 2ta ish urini bor": "job_offer",
    "1 kishi yana kk": "job_offer",
    # people looking for work
    "Akalar ertaga ish bolsa bir kishi bor": "job_seeker",
    "menga ish kerak": "job_seeker",
    "Ish bormi?": "job_seeker",
    "Asalomu alekum akalar 2kishiga ish bormi bosa aytib yuvorilar": "job_seeker",
    "외국인 일자리 구합니다 단순업무 식당 공장 서울 동대문거주": "job_seeker",
    "Bizam chiqamiz aka odam kerak bop qolsa": "job_seeker",
    # everything else
    "7 sentabr uchaman pochta bolsa olib ketaman": "cargo",
    "Kyongju tegudan daeso. Chongju ga ketaman. Moshnada 4kshiga joy bor. 01065707737": "travel",
    "ertaga saxar 대구 경산dan Seulga borib qaytamiz ketuvchilar bolsa 2 kishiga joy bor 01080971894": "travel",
    "KIA MORNING LPG Yili-2010 Yurgani-236.***km Balonlari 90% Avtomat karopka 26,27ming wonga": "sale",
    "iPhone 17 sotiladi 1.400.000won": "sale",
    "Gachon atrofida one room bor . Volse 600 ming. Sheriklikka odam kerak. 2 kishi turiladi": "sale",
    "Koreya boylab taxi xizmati. (Faqat shaharlararo). Kelishilgan xolda!": "service",
    "Помогу с деньгами, отпиши нужную сумму": "service",
    "Нужны 5 мужчин на завод, оплата каждый день": "job_offer",
    "Bor qancha berasz": "chat",
    "1 kishi bor": "chat",
    "Ertaga ertalab soat 3-4larga Ansongdan mokpoga boradigan 1 kish bor edi": "chat",
}


class JobFilterTests(unittest.TestCase):
    def test_known_messages(self):
        for text, kind in CASES.items():
            with self.subTest(text=text[:50]):
                self.assertEqual(classify_post(text), kind)

    def test_forwarded_posts_are_judged_by_their_job_text(self):
        header = "⚠️ Yangi xabar ma'lumotlari:\nGuruh: Daeso arbayt\nXabar egasi: Ali\nXabar vaqti: 2026-09-01 10:00\n\nXabar matni:\n"
        self.assertTrue(is_job_post(header + "Ertaga 3 kishiga ish bor 140 dan"))
        self.assertFalse(is_job_post(header + "1 kishi bor"))

    def test_any_input_gets_a_kind(self):
        for value in ("", "   ", "👍", None):
            self.assertIn(classify_post(value), KINDS)


if __name__ == "__main__":
    unittest.main()
