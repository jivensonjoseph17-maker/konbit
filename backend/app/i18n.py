"""
Konbit — Tradiksyon mesaj backend yo
Chemen: backend/app/i18n.py

Kòd la ekri tout mesaj erè yo an KREYÒL (lang pa defo a). Anvan repons lan
pati, main.py pase `detail` la nan `translate_detail()` dapre header
Accept-Language la. api.js mete header sa a sou chak rekèt ak lang moun nan
chwazi a.

Pou ajoute yon tradiksyon: kopye mesaj kreyòl la EGZAKTEMAN jan li ye nan
HTTPException(detail="...") oswa ValueError("...") epi ajoute yon liy
(kreyòl, franse, angle) nan _ROWS. Pou mesaj ki gen yon valè ladan
(f-string), ajoute yon liy nan PATTERNS. Yon mesaj ki pa nan katalòg la
rete an kreyòl — anyen pa kase.

Pou wè sa ki manke (nan backend\\):
    python scripts/i18n_missing.py
"""

import re
from http import HTTPStatus
from typing import Any, Optional

# Lang backend la gen mesaj erè pou yo (katalòg ki anba a).
SUPPORTED = ("ht", "fr", "en")
DEFAULT = "ht"

# Lang yon itilizatè ka chwazi pou kont li (frontend/i18n/*.json).
# Si backend la pa gen katalòg pou lang lan, api.js voye angle kòm rezèv
# ("es, en;q=0.5"), kidonk mesaj erè yo parèt an angle.
UI_LANGUAGES = (
    "ht", "fr", "en", "es", "pt", "zh", "ar", "hi", "bn", "ru",
    "ja", "de", "it", "ko", "tr", "vi", "id", "sw", "nl", "pl",
)


def resolve_language(header: Optional[str]) -> str:
    """'fr-FR,fr;q=0.9,en;q=0.8' → 'fr'. Premye lang nou konnen an genyen."""
    if not header:
        return DEFAULT
    for part in header.split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in SUPPORTED:
            return code
    return DEFAULT


def requested_language(header: Optional[str]) -> str:
    """Premye lang nan header la ki pami UI_LANGUAGES — pou sere nan kont lan."""
    if not header:
        return DEFAULT
    for part in header.split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in UI_LANGUAGES:
            return code
    return DEFAULT


# ---------------------------------------------------------------------------
# MESAJ FIKS — (kreyòl egzak, franse, angle)
# ---------------------------------------------------------------------------

_ROWS: list[tuple[str, str, str]] = [
    # --- Jenerik / main.py ---
    ("Done ou voye yo pa valab.",
     "Les données envoyées ne sont pas valides.",
     "The data you sent is not valid."),
    ("Yon erè entèn rive.",
     "Une erreur interne s'est produite.",
     "An internal error occurred."),

    # --- deps.py ---
    ("Nou pa ka verifye idantite w.",
     "Nous ne pouvons pas vérifier votre identité.",
     "We could not verify your identity."),
    ("Ou pa gen dwa pou aksyon sa a.",
     "Vous n'avez pas le droit d'effectuer cette action.",
     "You are not allowed to perform this action."),
    ("Kont ou a pa lye ak yon dosye anplwaye.",
     "Votre compte n'est lié à aucun dossier d'employé.",
     "Your account is not linked to an employee record."),
    ("Super admin dwe chwazi yon òganizasyon esplisitman.",
     "Le super administrateur doit choisir une organisation explicitement.",
     "The super admin must choose an organization explicitly."),
    ("Kont ou a pa lye ak okenn òganizasyon.",
     "Votre compte n'est lié à aucune organisation.",
     "Your account is not linked to any organization."),
    ("Òganizasyon an pa jwenn.",
     "Organisation introuvable.",
     "Organization not found."),

    # --- auth.py ---
    ("Imel oswa modpas la pa kòrèk.",
     "L'e-mail ou le mot de passe est incorrect.",
     "The email or password is incorrect."),
    ("Kont lan bloke apre twòp esè. Kontakte administratè w la.",
     "Le compte est bloqué après trop de tentatives. Contactez votre administrateur.",
     "The account is locked after too many attempts. Contact your administrator."),
    ("Kont sa a dezaktive.",
     "Ce compte est désactivé.",
     "This account is deactivated."),
    ("Yon kont ak imel sa a deja egziste.",
     "Un compte avec cet e-mail existe déjà.",
     "An account with this email already exists."),
    ("Nou pa t ka kreye kont lan.",
     "Nous n'avons pas pu créer le compte.",
     "We could not create the account."),
    ("Token an pa valab oswa li ekspire.",
     "Le jeton n'est pas valide ou il a expiré.",
     "The token is invalid or has expired."),
    ("Kont lan pa disponib.",
     "Le compte n'est pas disponible.",
     "The account is not available."),
    ("Modpas aktyèl la pa kòrèk.",
     "Le mot de passe actuel est incorrect.",
     "The current password is incorrect."),
    ("Nouvo modpas la dwe diferan de ansyen an.",
     "Le nouveau mot de passe doit être différent de l'ancien.",
     "The new password must be different from the old one."),
    ("Lang sa a pa disponib.",
     "Cette langue n'est pas disponible.",
     "This language is not available."),

    # --- app/auth.py (ansyen fichye) ---
    ("Imèl oswa modpas la pa kòrèk",
     "L'e-mail ou le mot de passe est incorrect",
     "The email or password is incorrect"),
    ("Imèl sa a deja anrejistre",
     "Cet e-mail est déjà enregistré",
     "This email is already registered"),

    # --- security.py (règ modpas) ---
    ("Modpas la dwe gen omwen yon chif.",
     "Le mot de passe doit contenir au moins un chiffre.",
     "The password must contain at least one digit."),
    ("Modpas la dwe gen omwen yon lèt.",
     "Le mot de passe doit contenir au moins une lettre.",
     "The password must contain at least one letter."),
    ("Modpas sa a twò komen.",
     "Ce mot de passe est trop courant.",
     "This password is too common."),

    # --- schemas.py ---
    ("Lyen an dwe kòmanse ak https:// (oswa http://).",
     "Le lien doit commencer par https:// (ou http://).",
     "The link must start with https:// (or http://)."),
    ("Lyen an twò long (500 karaktè maksimòm).",
     "Le lien est trop long (500 caractères maximum).",
     "The link is too long (500 characters maximum)."),
    ("Dat nesans lan pa sanble kòrèk.",
     "La date de naissance ne semble pas correcte.",
     "The date of birth does not look correct."),
    ("Ou bezwen yon imel pou kreye kont koneksyon an.",
     "Il faut un e-mail pour créer le compte de connexion.",
     "An email is required to create the login account."),
    ("Dat la dwe gen fizo orè (egz: 2026-10-01T14:00:00Z).",
     "La date doit inclure un fuseau horaire (ex. : 2026-10-01T14:00:00Z).",
     "The date must include a time zone (e.g. 2026-10-01T14:00:00Z)."),
    ("Salè minimòm nan pa ka pi wo pase salè maksimòm nan.",
     "Le salaire minimum ne peut pas dépasser le salaire maximum.",
     "The minimum salary cannot be higher than the maximum salary."),
    ("Anplwaye a dwe gen omwen 16 an.",
     "L'employé doit avoir au moins 16 ans.",
     "The employee must be at least 16 years old."),
    ("Dat fen an pa ka anvan dat kòmansman an.",
     "La date de fin ne peut pas précéder la date de début.",
     "The end date cannot be before the start date."),
    ("Yon demann konje pa ka depase yon ane.",
     "Une demande de congé ne peut pas dépasser un an.",
     "A leave request cannot exceed one year."),
    ("Dat peyman an pa ka anvan fen peryòd la.",
     "La date de paiement ne peut pas précéder la fin de la période.",
     "The payment date cannot be before the end of the period."),

    # --- Rekritman: òf travay, aplikasyon, antrevi ---
    ("Biznis la pa jwenn.",
     "Entreprise introuvable.",
     "Business not found."),
    ("Òf travay la pa disponib.",
     "L'offre d'emploi n'est pas disponible.",
     "The job posting is not available."),
    ("Òf travay la pa jwenn.",
     "Offre d'emploi introuvable.",
     "Job posting not found."),
    ("Òf travay la fèmen.",
     "L'offre d'emploi est fermée.",
     "The job posting is closed."),
    ("Aplikasyon an pa jwenn.",
     "Candidature introuvable.",
     "Application not found."),
    ("Antrevi a pa jwenn.",
     "Entretien introuvable.",
     "Interview not found."),
    ("Kandida a deja anboche.",
     "Le candidat est déjà embauché.",
     "The candidate has already been hired."),
    ("Pou anboche yon kandida, sèvi ak POST /api/offers/{id}/hire — li kreye dosye anplwaye a.",
     "Pour embaucher un candidat, utilisez POST /api/offers/{id}/hire — il crée le dossier de l'employé.",
     "To hire a candidate, use POST /api/offers/{id}/hire — it creates the employee record."),
    ("Moun k ap fè antrevi a pa jwenn.",
     "L'intervieweur est introuvable.",
     "Interviewer not found."),
    ("Salè minimòm nan pa ka pi wo pase maksimòm nan.",
     "Le salaire minimum ne peut pas dépasser le maximum.",
     "The minimum salary cannot be higher than the maximum."),
    ("Pou chanje estati a, sèvi ak Pibliye, Fèmen oswa Louvri ankò.",
     "Pour changer le statut, utilisez Publier, Fermer ou Rouvrir.",
     "To change the status, use Publish, Close or Reopen."),
    ("Dwe gen omwen yon pòs louvri.",
     "Il doit y avoir au moins un poste ouvert.",
     "There must be at least one opening."),
    ("Òf la deja pibliye.",
     "L'offre est déjà publiée.",
     "The posting is already published."),
    ("Ajoute yon deskripsyon anvan ou pibliye.",
     "Ajoutez une description avant de publier.",
     "Add a description before publishing."),
    ("Sèlman yon òf ki FÈMEN ka louvri ankò.",
     "Seule une offre FERMÉE peut être rouverte.",
     "Only a CLOSED posting can be reopened."),
    ("Sèlman yon bouyon ka efase. Fèmen òf la pito.",
     "Seul un brouillon peut être supprimé. Fermez plutôt l'offre.",
     "Only a draft can be deleted. Close the posting instead."),

    # --- Kesyon aplikasyon ---
    ("Kesyon an pa jwenn.",
     "Question introuvable.",
     "Question not found."),
    ("Kesyon sa a pa gen opsyon.",
     "Cette question n'a pas d'options.",
     "This question has no options."),
    ("Yon kesyon pa defo pa ka efase. Dezaktive l pito.",
     "Une question par défaut ne peut pas être supprimée. Désactivez-la plutôt.",
     "A default question cannot be deleted. Deactivate it instead."),
    ("Kandida deja reponn kesyon sa a. Dezaktive l pito, pou repons yo pa pèdi.",
     "Des candidats ont déjà répondu à cette question. Désactivez-la plutôt, pour ne pas perdre les réponses.",
     "Candidates have already answered this question. Deactivate it instead so the answers are not lost."),
    ("Yon kesyon chwa bezwen ant 2 ak 30 opsyon.",
     "Une question à choix doit avoir entre 2 et 30 options.",
     "A choice question needs between 2 and 30 options."),
    ("Chak opsyon dwe gen 100 karaktè maksimòm.",
     "Chaque option doit avoir 100 caractères maximum.",
     "Each option can have at most 100 characters."),
    ("Yon kondisyon bezwen kesyon an AK repons lan.",
     "Une condition exige la question ET la réponse.",
     "A condition needs both the question AND the answer."),
    ("Kondisyon an dwe 'true' oswa 'false'.",
     "La condition doit être 'true' ou 'false'.",
     "The condition must be 'true' or 'false'."),
    ("Kondisyon an dwe youn nan opsyon kesyon an.",
     "La condition doit être l'une des options de la question.",
     "The condition must be one of the question's options."),
    ("Yon kondisyon ka depann sèlman de yon kesyon wi/non oswa yon sèl chwa.",
     "Une condition ne peut dépendre que d'une question oui/non ou à choix unique.",
     "A condition can only depend on a yes/no or single-choice question."),

    # Mòso "«Kesyon»: ..." (validate_answers mete non kesyon an devan)
    ("repons lan dwe yon tèks.",
     "la réponse doit être un texte.",
     "the answer must be text."),
    ("reponn wi oswa non.",
     "répondez oui ou non.",
     "answer yes or no."),
    ("chwazi youn nan opsyon yo.",
     "choisissez l'une des options.",
     "choose one of the options."),
    ("chwazi nan opsyon yo.",
     "choisissez parmi les options.",
     "choose from the options."),
    ("mete yon chif.",
     "saisissez un nombre.",
     "enter a number."),
    ("chif la pa valab.",
     "le nombre n'est pas valide.",
     "the number is not valid."),
    ("dat la pa valab (AAAA-MM-JJ).",
     "la date n'est pas valide (AAAA-MM-JJ).",
     "the date is not valid (YYYY-MM-DD)."),
    ("mete yon lyen.",
     "saisissez un lien.",
     "enter a link."),
    ("kalite kesyon an pa konnen.",
     "type de question inconnu.",
     "unknown question type."),

    # --- Pwopozisyon (offers.py) ---
    ("Pwopozisyon an pa jwenn.",
     "Offre d'embauche introuvable.",
     "Offer not found."),
    ("Pwopozisyon an deja voye.",
     "L'offre d'embauche a déjà été envoyée.",
     "The offer has already been sent."),
    ("Dat ekspirasyon an deja pase. Chanje l anvan.",
     "La date d'expiration est déjà passée. Modifiez-la d'abord.",
     "The expiration date has already passed. Change it first."),
    ("Pwopozisyon an ekspire. Kreye yon nouvo.",
     "L'offre d'embauche a expiré. Créez-en une nouvelle.",
     "The offer has expired. Create a new one."),
    ("Sèlman yon bouyon ka efase.",
     "Seul un brouillon peut être supprimé.",
     "Only a draft can be deleted."),
    ("Anbochaj la pa pase. Anyen pa sere. Eseye ankò oswa kontakte sipò.",
     "L'embauche a échoué. Rien n'a été enregistré. Réessayez ou contactez le support.",
     "The hire failed. Nothing was saved. Try again or contact support."),

    # --- Anplwaye ---
    ("Anplwaye a pa jwenn.",
     "Employé introuvable.",
     "Employee not found."),
    ("Anplwaye a deja pa nan biznis la.",
     "L'employé ne fait déjà plus partie de l'entreprise.",
     "The employee is already no longer with the company."),
    ("Depatman an pa jwenn.",
     "Département introuvable.",
     "Department not found."),
    ("Pozisyon an pa jwenn.",
     "Poste introuvable.",
     "Position not found."),
    ("Manadjè a pa jwenn.",
     "Manager introuvable.",
     "Manager not found."),
    ("Ou pa gen dwa modifye dosye sa a.",
     "Vous n'avez pas le droit de modifier ce dossier.",
     "You are not allowed to edit this record."),
    ("Chanjman sa a ap kreye yon bouk nan òganigram lan.",
     "Ce changement créerait une boucle dans l'organigramme.",
     "This change would create a loop in the org chart."),
    ("Anplwaye a pa gen kont koneksyon.",
     "L'employé n'a pas de compte de connexion.",
     "The employee has no login account."),
    ("Kont koneksyon an pa jwenn.",
     "Compte de connexion introuvable.",
     "Login account not found."),

    # --- Prezans (attendance.py) ---
    ("Ou pa ka klòk in: estati w se pa aktif.",
     "Vous ne pouvez pas pointer l'arrivée : votre statut n'est pas actif.",
     "You cannot clock in: your status is not active."),
    ("Ou pa gen okenn jounen ki louvri. Fè klòk in anvan.",
     "Vous n'avez aucune journée ouverte. Pointez l'arrivée d'abord.",
     "You have no open shift. Clock in first."),
    ("Antre a pa jwenn.",
     "Pointage introuvable.",
     "Time entry not found."),
    ("Manadjè a deja apwouve èdtan peryòd sa a. Retire apwobasyon an anvan ou korije l — manadjè a ap dwe apwouve ankò.",
     "Le manager a déjà approuvé les heures de cette période. Retirez l'approbation avant de corriger — le manager devra approuver à nouveau.",
     "The manager has already approved this period's hours. Remove the approval before correcting — the manager will need to approve again."),
    ("Klòk out la pa ka anvan oswa egal ak klòk in lan.",
     "L'heure de sortie ne peut pas être antérieure ou égale à l'heure d'arrivée.",
     "Clock-out cannot be before or equal to clock-in."),

    # --- Konje (leaves.py) ---
    ("Demann lan pa jwenn.",
     "Demande introuvable.",
     "Request not found."),
    ("Ou pa ka fè demann konje: estati w se pa aktif.",
     "Vous ne pouvez pas demander de congé : votre statut n'est pas actif.",
     "You cannot request leave: your status is not active."),
    ("Ou gen yon demann ki kouvri menm jou sa yo deja.",
     "Vous avez déjà une demande qui couvre ces mêmes jours.",
     "You already have a request covering these same days."),
    ("Peryòd la pa gen okenn jou travay (sèlman wikenn).",
     "La période ne contient aucun jour ouvré (seulement le week-end).",
     "The period has no working days (weekend only)."),
    ("Se pa demann ou.",
     "Ce n'est pas votre demande.",
     "This is not your request."),
    ("Demann lan deja anile.",
     "La demande est déjà annulée.",
     "The request is already cancelled."),
    ("Ou pa ka anile yon konje ki deja kòmanse. Pale ak HR.",
     "Vous ne pouvez pas annuler un congé déjà commencé. Parlez aux RH.",
     "You cannot cancel leave that has already started. Talk to HR."),
    ("Ou pa gen dwa pou deside sou demann sa a.",
     "Vous n'avez pas le droit de statuer sur cette demande.",
     "You are not allowed to decide on this request."),

    # --- Peyòl (payroll.py) ---
    ("Peryòd la pa jwenn.",
     "Période introuvable.",
     "Period not found."),
    ("Fich peye a pa jwenn.",
     "Fiche de paie introuvable.",
     "Payslip not found."),
    ("Peyòl sa a deja peye. Ou pa ka rejenere l.",
     "Cette paie est déjà payée. Vous ne pouvez pas la régénérer.",
     "This payroll is already paid. You cannot regenerate it."),
    ("Pa gen fich peye. Rele /run anvan.",
     "Aucune fiche de paie. Lancez /run d'abord.",
     "There are no payslips. Call /run first."),
    ("Ou dwe apwouve peyòl la anvan ou make l peye.",
     "Vous devez approuver la paie avant de la marquer comme payée.",
     "You must approve the payroll before marking it as paid."),
    ("Fich peye sa a poko apwouve.",
     "Cette fiche de paie n'est pas encore approuvée.",
     "This payslip is not approved yet."),
    ("Anplwaye a pa gen nimewo kont labank pou depo dirèk.",
     "L'employé n'a pas de numéro de compte bancaire pour le virement direct.",
     "The employee has no bank account number for direct deposit."),

    # --- Tan travay (timesheets.py) ---
    ("Peyòl peryòd sa a deja apwouve oswa peye. Èdtan yo pa ka chanje ankò.",
     "La paie de cette période est déjà approuvée ou payée. Les heures ne peuvent plus changer.",
     "Payroll for this period is already approved or paid. Hours can no longer change."),
    ("Ou pa gen dwa pou paj sa a.",
     "Vous n'avez pas accès à cette page.",
     "You do not have access to this page."),
    ("Ou pa ka apwouve èdtan moun sa a.",
     "Vous ne pouvez pas approuver les heures de cette personne.",
     "You cannot approve this person's hours."),
    ("Ou pa ka deside sou èdtan moun sa a.",
     "Vous ne pouvez pas statuer sur les heures de cette personne.",
     "You cannot decide on this person's hours."),
    ("Pa gen desizyon pou retire.",
     "Aucune décision à retirer.",
     "There is no decision to remove."),

    # --- Orè travay (schedules.py) ---
    ("Ou pa ka planifye orè moun sa a.",
     "Vous ne pouvez pas planifier l'horaire de cette personne.",
     "You cannot schedule this person."),
    ("Modèl orè a pa jwenn.",
     "Modèle d'horaire introuvable.",
     "Shift template not found."),
    ("Orè a pa jwenn.",
     "Horaire introuvable.",
     "Shift not found."),
    ("Yon orè pa ka depase 16 èdtan.",
     "Un horaire ne peut pas dépasser 16 heures.",
     "A shift cannot exceed 16 hours."),
    ("Poz la pa ka pi long pase orè a.",
     "La pause ne peut pas être plus longue que l'horaire.",
     "The break cannot be longer than the shift."),
    ("Chwazi yon modèl oswa bay lè kòmansman ak lè fen.",
     "Choisissez un modèle ou indiquez l'heure de début et de fin.",
     "Choose a template or give a start and end time."),

    # --- Fidbak ak evalyasyon (feedback.py) ---
    ("Fidbak la pa jwenn.",
     "Commentaire introuvable.",
     "Feedback not found."),
    ("Evalyasyon an pa jwenn.",
     "Évaluation introuvable.",
     "Review not found."),
    ("Ou pa gen dwa pou bwat sa a.",
     "Vous n'avez pas accès à cette boîte.",
     "You do not have access to this inbox."),
    ("Ou pa gen dwa wè fidbak sa a.",
     "Vous n'avez pas le droit de voir ce commentaire.",
     "You are not allowed to see this feedback."),
    ("Ou pa gen dwa reponn fidbak.",
     "Vous n'avez pas le droit de répondre aux commentaires.",
     "You are not allowed to respond to feedback."),
    ("Ou pa ka kite fidbak sou tèt ou.",
     "Vous ne pouvez pas laisser un commentaire sur vous-même.",
     "You cannot leave feedback about yourself."),
    ("Ou pa gen dwa evalye moun.",
     "Vous n'avez pas le droit d'évaluer des personnes.",
     "You are not allowed to review people."),
    ("Ou ka evalye sèlman moun ki anba w.",
     "Vous ne pouvez évaluer que les personnes sous votre responsabilité.",
     "You can only review people who report to you."),
    ("Ou pa ka evalye tèt ou.",
     "Vous ne pouvez pas vous évaluer vous-même.",
     "You cannot review yourself."),
    ("Ou pa gen dwa pou lis sa a.",
     "Vous n'avez pas accès à cette liste.",
     "You do not have access to this list."),
    ("Evalyasyon sa a poko finalize.",
     "Cette évaluation n'est pas encore finalisée.",
     "This review is not finalized yet."),
    ("Evalyasyon an finalize. Ou pa ka modifye l ankò.",
     "L'évaluation est finalisée. Vous ne pouvez plus la modifier.",
     "The review is finalized. You can no longer edit it."),
    ("Se pa ou ki ekri evalyasyon sa a.",
     "Ce n'est pas vous qui avez rédigé cette évaluation.",
     "You did not write this review."),
    ("Se pa evalyasyon w.",
     "Ce n'est pas votre évaluation.",
     "This is not your review."),
    ("Evalyasyon an poko finalize.",
     "L'évaluation n'est pas encore finalisée.",
     "The review is not finalized yet."),
    ("Li deja finalize.",
     "Elle est déjà finalisée.",
     "It is already finalized."),
    ("Mete yon nòt jeneral (1-5) anvan ou finalize.",
     "Attribuez une note globale (1-5) avant de finaliser.",
     "Give an overall rating (1-5) before finalizing."),

    # --- Fòmasyon (training.py) ---
    ("Kou a pa jwenn.",
     "Cours introuvable.",
     "Course not found."),
    ("Sa se yon kou Konbit bay. Ou pa ka modifye l.",
     "Ce cours est fourni par Konbit. Vous ne pouvez pas le modifier.",
     "This course is provided by Konbit. You cannot edit it."),
    ("Leson an pa jwenn.",
     "Leçon introuvable.",
     "Lesson not found."),
    ("Kou a poko pibliye.",
     "Le cours n'est pas encore publié.",
     "The course is not published yet."),
    ("Kou a pa gen okenn leson. Ajoute omwen youn anvan.",
     "Le cours n'a aucune leçon. Ajoutez-en au moins une d'abord.",
     "The course has no lessons. Add at least one first."),
    ("Lis la dwe gen egzakteman tout leson kou a, yon sèl fwa chak.",
     "La liste doit contenir exactement toutes les leçons du cours, une seule fois chacune.",
     "The list must contain exactly all of the course's lessons, each only once."),
    ("Pibliye kou a anvan ou asiyen l.",
     "Publiez le cours avant de l'assigner.",
     "Publish the course before assigning it."),
    ("Ou pa enskri nan kou sa a.",
     "Vous n'êtes pas inscrit à ce cours.",
     "You are not enrolled in this course."),
    ("Ou pa gen dwa pou rapò sa a.",
     "Vous n'avez pas accès à ce rapport.",
     "You do not have access to this report."),

    # --- companies.py (ansyen router, pa aktif) ---
    ("Ou deja gen yon konpayi ki anrejistre.",
     "Vous avez déjà une entreprise enregistrée.",
     "You already have a registered company."),
    ("Ou pa gen okenn konpayi ki anrejistre.",
     "Vous n'avez aucune entreprise enregistrée.",
     "You have no registered company."),
    ("Konpayi sa a pa egziste.",
     "Cette entreprise n'existe pas.",
     "This company does not exist."),
    ("Konpayi pa jwenn.",
     "Entreprise introuvable.",
     "Company not found."),
    ("Fòma fichiye sa a pa sipòte. Sèvi ak PNG, JPG oswa WEBP.",
     "Ce format de fichier n'est pas pris en charge. Utilisez PNG, JPG ou WEBP.",
     "This file format is not supported. Use PNG, JPG or WEBP."),
]

MESSAGES: dict[str, dict[str, str]] = {ht: {"fr": fr, "en": en} for ht, fr, en in _ROWS}


# ---------------------------------------------------------------------------
# MESAJ AK VALÈ LADAN (f-string)
#
# Chak gwoup (?P<non>...) pase nan tradiksyon an jan li ye. Sèl eksepsyon:
# mo nan _VALUE_WORDS (egz: "okenn") tradui tou.
# ---------------------------------------------------------------------------

def _p(regex: str, fr: str, en: str) -> tuple[re.Pattern[str], dict[str, str]]:
    return re.compile(regex), {"fr": fr, "en": en}


PATTERNS: list[tuple[re.Pattern[str], dict[str, str]]] = [
    # --- auth / modpas ---
    _p(r"^Idantifyan '(?P<slug>.+)' la deja pran\. Chwazi yon lòt\.$",
       "L'identifiant '{slug}' est déjà pris. Choisissez-en un autre.",
       "The identifier '{slug}' is already taken. Choose another one."),
    _p(r"^Modpas la dwe gen omwen (?P<n>\d+) karaktè\.$",
       "Le mot de passe doit contenir au moins {n} caractères.",
       "The password must be at least {n} characters long."),

    # --- Kesyon aplikasyon ---
    _p(r"^Opsyon '(?P<value>.+)' la repete\.$",
       "L'option '{value}' est répétée.",
       "The option '{value}' is repeated."),
    _p(r"^Seksyon an dwe youn nan: (?P<items>.+)\.$",
       "La section doit être l'une de : {items}.",
       "The section must be one of: {items}."),
    _p(r"^Kesyon «(?P<label>.+)» depann de kesyon sa a\. Chanje l anvan\.$",
       "La question «{label}» dépend de cette question. Modifiez-la d'abord.",
       "The question “{label}” depends on this question. Change it first."),
    _p(r"^repons lan twò long \((?P<n>\d+) karaktè maksimòm\)\.$",
       "la réponse est trop longue ({n} caractères maximum).",
       "the answer is too long ({n} characters maximum)."),
    _p(r"^'(?P<value>.+)' pa youn nan opsyon yo\.$",
       "'{value}' ne fait pas partie des options.",
       "'{value}' is not one of the options."),

    # --- Aplikasyon / pwopozisyon ---
    _p(r"^Kandida a nan estati '(?P<s>[^']+)'\.$",
       "Le candidat est au statut '{s}'.",
       "The candidate is in status '{s}'."),
    _p(r"^Ou pa ka pase de '(?P<a>[^']+)' a '(?P<b>[^']+)'\. Etap ki posib: (?P<items>.+)\.$",
       "Impossible de passer de '{a}' à '{b}'. Étapes possibles : {items}.",
       "You cannot move from '{a}' to '{b}'. Possible steps: {items}."),
    _p(r"^Gen deja yon pwopozisyon aktif \(#(?P<id>\d+)\) pou kandida a\.$",
       "Il y a déjà une offre d'embauche active (#{id}) pour ce candidat.",
       "There is already an active offer (#{id}) for this candidate."),
    _p(r"^Pwopozisyon an nan estati '(?P<s>[^']+)'\. Sèlman yon bouyon ka modifye\.$",
       "L'offre d'embauche est au statut '{s}'. Seul un brouillon peut être modifié.",
       "The offer is in status '{s}'. Only a draft can be edited."),
    _p(r"^Pwopozisyon an nan estati '(?P<s>[^']+)'\. Kandida a dwe aksepte anvan\.$",
       "L'offre d'embauche est au statut '{s}'. Le candidat doit d'abord l'accepter.",
       "The offer is in status '{s}'. The candidate must accept it first."),
    _p(r"^Pwopozisyon an nan estati '(?P<s>[^']+)'\.$",
       "L'offre d'embauche est au statut '{s}'.",
       "The offer is in status '{s}'."),
    _p(r"^(?P<n>\d+) moun aplike\. Fèmen òf la olye ou efase l\.$",
       "{n} personne(s) ont postulé. Fermez l'offre au lieu de la supprimer.",
       "{n} people applied. Close the posting instead of deleting it."),

    # --- Anplwaye ---
    _p(r"^Nimewo '(?P<n>.+)' la deja pran\.$",
       "Le numéro '{n}' est déjà pris.",
       "Number '{n}' is already taken."),
    _p(r"^Yon kont ak imel '(?P<email>.+)' deja egziste\.$",
       "Un compte avec l'e-mail '{email}' existe déjà.",
       "An account with the email '{email}' already exists."),
    _p(r"^Ou pa ka chanje: (?P<items>.+)\.$",
       "Vous ne pouvez pas modifier : {items}.",
       "You cannot change: {items}."),

    # --- Prezans ---
    _p(r"^Ou deja klòk in depi (?P<h>\d+)è (?P<m>\d+)min\. Fè klòk out anvan\.$",
       "Vous avez pointé l'arrivée il y a {h} h {m} min. Pointez la sortie d'abord.",
       "You clocked in {h}h {m}m ago. Clock out first."),
    _p(r"^Jounen an gen plis pase (?P<n>\d+) èdtan\. Nou make l pou HR korije l\.$",
       "La journée dépasse {n} heures. Elle a été signalée aux RH pour correction.",
       "The shift is longer than {n} hours. It has been flagged for HR to correct."),

    # --- Konje ---
    _p(r"^Demann lan deja nan estati '(?P<s>[^']+)'\.$",
       "La demande est déjà au statut '{s}'.",
       "The request is already in status '{s}'."),
    _p(r"^Ou mande (?P<total>\S+) jou men ou gen sèlman (?P<left>\S+) jou ki rete\.$",
       "Vous demandez {total} jour(s) mais il ne vous en reste que {left}.",
       "You requested {total} day(s) but only have {left} left."),

    # --- Peyòl ---
    _p(r"^Peryòd la kouvri menm dat ak '(?P<name>.+)'\.$",
       "La période chevauche les dates de '{name}'.",
       "The period overlaps with the dates of '{name}'."),
    _p(r"^Èdtan (?P<n>\d+) moun poko apwouve pa manadjè yo: (?P<names>.+)\. Si ou kontinye, "
       r"yo ap touche salè de baz yo men PA èdtan siplemantè\.$",
       "Les heures de {n} personne(s) ne sont pas encore approuvées par les managers : {names}. "
       "Si vous continuez, elles recevront leur salaire de base mais PAS les heures supplémentaires.",
       "Hours for {n} people are not yet approved by their managers: {names}. "
       "If you continue, they will receive their base salary but NOT overtime."),
    _p(r"^Peryòd la nan estati '(?P<s>[^']+)'\. Ou pa ka chanje dat peman an\.$",
       "La période est au statut '{s}'. Vous ne pouvez pas changer la date de paiement.",
       "The period is in status '{s}'. You cannot change the payment date."),
    _p(r"^Peryòd la nan estati '(?P<s>[^']+)'\.$",
       "La période est au statut '{s}'.",
       "The period is in status '{s}'."),
    _p(r"^Fich yo te kalkile pou yon peman (?P<planned>\S+) \(retni sou bonis (?P<prate>\S+)\), "
       r"men peman an fèt (?P<paid>\S+) \(retni (?P<arate>\S+)\)\. (?P<n>\d+) fich gen bonis oswa "
       r"èdtan siplemantè\. Chanje dat peman an pou (?P<paid2>\S+), verifye fich yo, apwouve peyòl "
       r"la ankò, epi make l peye\.$",
       "Les fiches ont été calculées pour un paiement le {planned} (retenue sur les primes {prate}), "
       "mais le paiement a lieu le {paid} (retenue {arate}). {n} fiche(s) comportent des primes ou "
       "des heures supplémentaires. Changez la date de paiement pour le {paid2}, vérifiez les fiches, "
       "approuvez de nouveau la paie, puis marquez-la comme payée.",
       "The payslips were calculated for a payment on {planned} ({prate} bonus withholding), "
       "but the payment is made on {paid} ({arate} withholding). {n} payslip(s) include bonuses or "
       "overtime. Change the payment date to {paid2}, review the payslips, approve the payroll "
       "again, then mark it as paid."),
    _p(r"^Fich la nan estati '(?P<s>[^']+)'\. Sèlman yon bouyon ka ajiste\.$",
       "La fiche est au statut '{s}'. Seul un brouillon peut être ajusté.",
       "The payslip is in status '{s}'. Only a draft can be adjusted."),
    _p(r"^Anplwaye a pa gen nimewo telefòn pou (?P<m>.+)\.$",
       "L'employé n'a pas de numéro de téléphone pour {m}.",
       "The employee has no phone number for {m}."),

    # --- Tan travay ---
    _p(r"^Peryòd la poko fini \((?P<d>[^)]+)\)\. Ou ka apwouve èdtan yo sèlman apre dènye jou a\.$",
       "La période n'est pas terminée ({d}). Vous ne pouvez approuver les heures qu'après le dernier jour.",
       "The period has not ended ({d}). You can approve hours only after the last day."),
    _p(r"^(?P<n>\d+) pwentaj toujou louvri oswa san lè sòti\. Voye fèy la bay HR pou yo korije l anvan\.$",
       "{n} pointage(s) encore ouvert(s) ou sans heure de sortie. Renvoyez la feuille aux RH pour correction d'abord.",
       "{n} time entries are still open or missing a clock-out. Send the timesheet to HR to fix first."),

    # --- Fòmasyon ---
    _p(r"^(?P<n>\d+) anplwaye enskri nan kou sa a\. Retire l nan piblikasyon olye ou efase l\.$",
       "{n} employé(s) inscrit(s) à ce cours. Dépubliez-le au lieu de le supprimer.",
       "{n} employees are enrolled in this course. Unpublish it instead of deleting it."),
    _p(r"^Ou fini (?P<p>\S+)% nan kou a\. Gade tout leson obligatwa yo anvan\.$",
       "Vous avez terminé {p} % du cours. Regardez d'abord toutes les leçons obligatoires.",
       "You have completed {p}% of the course. Watch all required lessons first."),
    _p(r"^Nòt ou a se (?P<s>\S+)%\. Ou bezwen omwen (?P<p>\S+)% pou pase\.$",
       "Votre note est de {s} %. Il vous faut au moins {p} % pour réussir.",
       "Your score is {s}%. You need at least {p}% to pass."),
]

_VALUE_WORDS: dict[str, dict[str, str]] = {
    "okenn": {"fr": "aucune", "en": "none"},
}


# ---------------------------------------------------------------------------
# REPONS FÒM APLIKASYON (validate_answers)
#
# Mesaj la konpoze: "Kesyon obligatwa ki manke: «A», «B». «C»: mete yon chif."
# Non kesyon yo (ekri pa biznis la) pa tradui; rès la tradui mòso pa mòso.
# ---------------------------------------------------------------------------

_MISSING_RE = re.compile(r"^Kesyon obligatwa ki manke: (?P<items>«.*?»)\.(?= «|$)")
_ANSWER_LABEL_RE = re.compile(r"«([^»]*)»: ")
_MISSING_TEMPLATES = {
    "fr": "Questions obligatoires manquantes : {items}.",
    "en": "Missing required questions: {items}.",
}


def _translate_answer_problems(message: str, lang: str) -> Optional[str]:
    if not (message.startswith("Kesyon obligatwa ki manke: ") or message.startswith("«")):
        return None

    out: list[str] = []
    rest = message
    missing = _MISSING_RE.match(rest)
    if missing:
        out.append(_MISSING_TEMPLATES[lang].format(items=missing.group("items")))
        rest = rest[missing.end():].lstrip()

    if rest:
        starts = list(_ANSWER_LABEL_RE.finditer(rest))
        if not starts or starts[0].start() != 0:
            return None
        for i, match in enumerate(starts):
            end = starts[i + 1].start() if i + 1 < len(starts) else len(rest)
            fragment = rest[match.end():end].strip()
            out.append(f"«{match.group(1)}»: {translate(fragment, lang)}")

    return " ".join(out) if out else None


# ---------------------------------------------------------------------------
# MESAJ STARLETTE / FASTAPI (an angle pa defo, menm pou kreyòl)
# ---------------------------------------------------------------------------

FRAMEWORK: dict[str, dict[str, str]] = {
    "Not authenticated": {
        "ht": "Ou dwe konekte.",
        "fr": "Vous devez être connecté.",
        "en": "You must be signed in.",
    },
    HTTPStatus.NOT_FOUND.phrase: {
        "ht": "Sa ou chèche a pa egziste.",
        "fr": "La ressource demandée n'existe pas.",
        "en": "The requested resource does not exist.",
    },
    HTTPStatus.METHOD_NOT_ALLOWED.phrase: {
        "ht": "Metòd sa a pa pèmèt.",
        "fr": "Cette méthode n'est pas autorisée.",
        "en": "This method is not allowed.",
    },
}


def translate(message: Any, lang: str) -> Any:
    """Tradui yon mesaj. Sa ki pa yon tèks, oswa ki pa nan katalòg la, pase jan l ye."""
    if not isinstance(message, str):
        return message

    framework = FRAMEWORK.get(message)
    if framework:
        return framework.get(lang, framework[DEFAULT])

    if lang == DEFAULT or lang not in SUPPORTED:
        return message

    entry = MESSAGES.get(message)
    if entry:
        return entry[lang]

    for pattern, templates in PATTERNS:
        match = pattern.match(message)
        if match:
            values = {
                key: _VALUE_WORDS.get(value, {}).get(lang, value)
                for key, value in match.groupdict().items()
            }
            return templates[lang].format(**values)

    composed = _translate_answer_problems(message, lang)
    if composed is not None:
        return composed

    return message


def translate_detail(detail: Any, lang: str) -> Any:
    """`detail` ka yon tèks oswa yon lis tèks (egz: règ modpas yo)."""
    if isinstance(detail, list):
        return [translate(item, lang) for item in detail]
    return translate(detail, lang)


# ---------------------------------------------------------------------------
# ERÈ VALIDASYON PYDANTIC
#
# Pydantic ekri mesaj li yo an angle ("Field required"). Nou ranplase yo
# dapre `type` erè a, nan tout twa lang yo — menm an kreyòl.
# ---------------------------------------------------------------------------

_INVALID_CHOICE = {
    "ht": "Valè sa a pa pami chwa yo.",
    "fr": "Cette valeur ne fait pas partie des choix.",
    "en": "This value is not one of the allowed choices.",
}
_INVALID_DATE = {
    "ht": "Dat la pa valab.",
    "fr": "La date n'est pas valide.",
    "en": "The date is not valid.",
}
_INVALID_DATETIME = {
    "ht": "Dat ak lè a pa valab.",
    "fr": "La date et l'heure ne sont pas valides.",
    "en": "The date and time are not valid.",
}
_INVALID_INT = {
    "ht": "Mete yon nonb antye.",
    "fr": "Saisissez un nombre entier.",
    "en": "Enter a whole number.",
}

PYDANTIC: dict[str, dict[str, str]] = {
    "missing": {
        "ht": "Jaden sa a obligatwa.",
        "fr": "Ce champ est obligatoire.",
        "en": "This field is required.",
    },
    "string_too_short": {
        "ht": "Omwen {min_length} karaktè.",
        "fr": "Au moins {min_length} caractères.",
        "en": "At least {min_length} characters.",
    },
    "string_too_long": {
        "ht": "Pa plis pase {max_length} karaktè.",
        "fr": "Pas plus de {max_length} caractères.",
        "en": "No more than {max_length} characters.",
    },
    "string_type": {
        "ht": "Mete yon tèks.",
        "fr": "Saisissez un texte.",
        "en": "Enter some text.",
    },
    "string_pattern_mismatch": {
        "ht": "Fòma a pa kòrèk.",
        "fr": "Le format n'est pas correct.",
        "en": "The format is not correct.",
    },
    "greater_than_equal": {
        "ht": "Dwe {ge} oswa plis.",
        "fr": "Doit être {ge} ou plus.",
        "en": "Must be {ge} or more.",
    },
    "greater_than": {
        "ht": "Dwe plis pase {gt}.",
        "fr": "Doit être supérieur à {gt}.",
        "en": "Must be greater than {gt}.",
    },
    "less_than_equal": {
        "ht": "Dwe {le} oswa mwens.",
        "fr": "Doit être {le} ou moins.",
        "en": "Must be {le} or less.",
    },
    "less_than": {
        "ht": "Dwe mwens pase {lt}.",
        "fr": "Doit être inférieur à {lt}.",
        "en": "Must be less than {lt}.",
    },
    "int_parsing": _INVALID_INT,
    "int_type": _INVALID_INT,
    "int_from_float": _INVALID_INT,
    "float_parsing": {
        "ht": "Mete yon nonb.",
        "fr": "Saisissez un nombre.",
        "en": "Enter a number.",
    },
    "bool_parsing": {
        "ht": "Reponn wi oswa non.",
        "fr": "Répondez oui ou non.",
        "en": "Answer yes or no.",
    },
    "date_parsing": _INVALID_DATE,
    "date_type": _INVALID_DATE,
    "date_from_datetime_parsing": _INVALID_DATE,
    "date_from_datetime_inexact": _INVALID_DATE,
    "datetime_parsing": _INVALID_DATETIME,
    "datetime_type": _INVALID_DATETIME,
    "datetime_from_date_parsing": _INVALID_DATETIME,
    "timezone_aware": {
        "ht": "Dat la bezwen yon fizo orè.",
        "fr": "La date doit inclure un fuseau horaire.",
        "en": "The date must include a time zone.",
    },
    "enum": _INVALID_CHOICE,
    "literal_error": _INVALID_CHOICE,
    "json_invalid": {
        "ht": "JSON la pa valab.",
        "fr": "Le JSON n'est pas valide.",
        "en": "The JSON is not valid.",
    },
}

_EMAIL_INVALID = {
    "ht": "Adrès imel la pa valab.",
    "fr": "L'adresse e-mail n'est pas valide.",
    "en": "The email address is not valid.",
}

_VALUE_ERROR_PREFIXES = ("Value error, ", "Assertion failed, ")


def validation_message(err: dict[str, Any], lang: str) -> str:
    """Yon mesaj klè pou yon erè Pydantic, nan lang moun nan."""
    err_type = err.get("type", "")
    raw = str(err.get("msg", ""))

    if err_type in ("value_error", "assertion_error"):
        if "valid email address" in raw:
            return _EMAIL_INVALID.get(lang, _EMAIL_INVALID[DEFAULT])
        for prefix in _VALUE_ERROR_PREFIXES:
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
                break
        # Mesaj pa nou yo (ValueError nan schemas.py) ekri an kreyòl.
        return translate(raw, lang)

    template = PYDANTIC.get(err_type)
    if template:
        try:
            return template.get(lang, template[DEFAULT]).format(**(err.get("ctx") or {}))
        except (KeyError, IndexError, ValueError):
            pass

    return raw