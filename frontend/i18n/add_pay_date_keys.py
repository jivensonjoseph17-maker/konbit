"""
Konbit — Ajoute 3 nouvo fraz "Dat peman" yo nan tout fichye lang yo
Chemen: frontend/i18n/add_pay_date_keys.py

Kouri l YON FWA depi konbit\\:
    python frontend\\i18n\\add_pay_date_keys.py

Li pa touche okenn lòt fraz. Si yon kle deja la, li kite l jan l ye.
Apre sa: python frontend\\i18n\\check_i18n.py  → tout lang yo dwe "konplè".
Ou ka efase fichye sa a apre.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

K_BTN = "Chanje dat la"
K_DONE = "Dat peman an chanje."
K_REOPEN = "Dat peman an chanje. {count} fich rekalkile: verifye yo epi apwouve pewòl la ankò."

NEW = {
    "ht": {K_BTN: K_BTN, K_DONE: K_DONE, K_REOPEN: K_REOPEN},
    "fr": {
        K_BTN: "Changer la date",
        K_DONE: "La date de paiement a été modifiée.",
        K_REOPEN: "La date de paiement a été modifiée. {count} fiche(s) recalculée(s) : "
                  "vérifiez-les puis approuvez de nouveau la paie.",
    },
    "en": {
        K_BTN: "Change date",
        K_DONE: "Payment date changed.",
        K_REOPEN: "Payment date changed. {count} payslip(s) recalculated: "
                  "review them and approve the payroll again.",
    },
    "es": {
        K_BTN: "Cambiar la fecha",
        K_DONE: "Se cambió la fecha de pago.",
        K_REOPEN: "Se cambió la fecha de pago. {count} recibo(s) recalculado(s): "
                  "revísalos y vuelve a aprobar la nómina.",
    },
    "pt": {
        K_BTN: "Alterar a data",
        K_DONE: "A data de pagamento foi alterada.",
        K_REOPEN: "A data de pagamento foi alterada. {count} holerite(s) recalculado(s): "
                  "revise-os e aprove a folha de pagamento novamente.",
    },
    "de": {
        K_BTN: "Datum ändern",
        K_DONE: "Zahlungsdatum geändert.",
        K_REOPEN: "Zahlungsdatum geändert. {count} Abrechnung(en) neu berechnet: "
                  "bitte prüfen und die Lohnabrechnung erneut genehmigen.",
    },
    "zh": {
        K_BTN: "更改日期",
        K_DONE: "支付日期已更改。",
        K_REOPEN: "支付日期已更改。已重新计算 {count} 张工资单：请核对后重新审批工资。",
    },
    "ar": {
        K_BTN: "تغيير التاريخ",
        K_DONE: "تم تغيير تاريخ الدفع.",
        K_REOPEN: "تم تغيير تاريخ الدفع. أُعيد حساب {count} من كشوف الرواتب: "
                  "راجعها ثم اعتمد الرواتب من جديد.",
    },
}


def main() -> None:
    for lang, entries in NEW.items():
        path = HERE / f"{lang}.json"
        if not path.exists():
            print(f"{lang:>3}: pa gen {path.name} — sote")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        added = 0
        for key, value in entries.items():
            if not data.get(key):
                data[key] = value
                added += 1
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{lang:>3}: {added} fraz ajoute")


if __name__ == "__main__":
    main()