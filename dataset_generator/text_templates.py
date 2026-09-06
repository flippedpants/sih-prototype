"""
FIR narrative templates for Phase D (schema spec Section 7).

Each template is a plain string with `{slot_name}` placeholders. Rendering
(see `render_template` in fir_generator.py) walks the string once, appending
literal text and slot values in order and recording the exact character span
of each inserted value as it is appended - never re-locating a value in the
finished text with something like `str.find()`, which would give the wrong
span for any value that happens to repeat (a common first name, a duplicate
mule account referenced in two stages, and so on).

Slot -> NER label mapping (`SLOT_LABELS`) says how each placeholder should be
labeled when it is actually filled in. `{phone}` is now used by a majority of
variants across every stage/subtype (previously only one variant had it,
which left PHONE badly under-represented in the generated corpus relative to
LOCATION/ORG) - added via new trailing clauses on existing variants (or, in a
couple of spots that already gestured at "the support number"/"the number
that called", by making that existing gesture concrete) rather than by
removing or rewording anything that was already there.
"""

SLOT_LABELS = {
    "victim_name": "PERSON",
    "impersonated_authority": "ORG",
    "amount": "AMOUNT",
    "account_ref": "ACCOUNT",
    "phone": "PHONE",
    "location": "LOCATION",
}

# Categorical authority choices for the digital_arrest narrative
# (I4C's documented impersonation targets), mapped to the display text
# actually inserted into the narrative.
DIGITAL_ARREST_AUTHORITIES = ["police", "cbi", "rbi", "customs", "narcotics", "ed"]

AUTHORITY_DISPLAY = {
    "police": "Cyber Crime Police",
    "cbi": "Central Bureau of Investigation (CBI)",
    "rbi": "Reserve Bank of India (RBI)",
    "customs": "Indian Customs Department",
    "narcotics": "Narcotics Control Bureau (NCB)",
    "ed": "Enforcement Directorate (ED)",
}

# Four-stage digital_arrest structure, matching I4C's documented pattern:
# impersonation -> intimidation -> confinement -> extortion.
DIGITAL_ARREST_TEMPLATES = {
    "impersonation": [
        "The complainant {victim_name} received a video call from an unknown "
        "number claiming to be from the {impersonated_authority}, stating that "
        "a parcel booked under the complainant's identity documents had been "
        "seized and was linked to an ongoing criminal case. The call was "
        "placed from {phone}.",

        "{victim_name} was contacted by a caller identifying himself as an "
        "officer of the {impersonated_authority}, who claimed that the "
        "complainant's mobile number, {phone}, had been used in a "
        "money-laundering case currently under investigation.",

        "A person representing themselves as an official of the "
        "{impersonated_authority} called {victim_name} and alleged that a "
        "courier addressed to the complainant contained banned substances, "
        "and that the matter had already been escalated for legal action.",

        "The complainant {victim_name}, residing in {location}, received a "
        "call from someone posing as an investigating officer of the "
        "{impersonated_authority}, who stated that the complainant's "
        "identity documents had been used to open a fraudulent bank account. "
        "The caller's number was later noted as {phone}.",

        "{victim_name} received a video call from a man in what appeared to "
        "be an official uniform, claiming to represent the "
        "{impersonated_authority}, and stating that a case had already been "
        "registered against the complainant in another state.",
    ],
    "intimidation": [
        "The caller warned {victim_name} that any refusal to cooperate would "
        "result in immediate arrest and public disclosure of the case to "
        "family members and employers. The threats continued to come from "
        "the same number, {phone}.",

        "The complainant was told that a non-bailable warrant had already "
        "been issued and that {victim_name}'s bank accounts would be frozen "
        "within the hour unless the matter was resolved directly with the "
        "officer on the call. {victim_name} was told to remain reachable at "
        "all times on {phone} for further instructions.",

        "{victim_name} was shown a fabricated arrest warrant bearing an "
        "official-looking seal and was told that failure to comply within "
        "thirty minutes would lead to a raid at the complainant's residence "
        "in {location}.",

        "The caller threatened that {victim_name}'s passport would be "
        "impounded and international travel blocked if the complainant did "
        "not remain on the call and follow further instructions. The number "
        "that called was {phone}.",

        "{victim_name} was told that the case had been marked sensitive and "
        "that any attempt to approach the local police station in "
        "{location} would result in additional charges being added. All "
        "further contact was to go through {phone}.",
    ],
    "confinement": [
        "{victim_name} was instructed to remain on video call continuously "
        "and not disconnect or leave the room, a tactic later identified as "
        "a 'digital arrest', until the demanded amount was paid. The caller "
        "was reachable throughout on {phone}.",

        "The complainant was directed to move to an isolated room, keep the "
        "camera on at all times, and avoid contact with any family member "
        "for the duration of the call.",

        "{victim_name} was kept under continuous video surveillance by the "
        "caller for several hours and was instructed not to inform anyone, "
        "including bank officials, about the nature of the call from "
        "{phone}.",

        "The caller insisted that {victim_name} stay visible on camera "
        "throughout, citing a 'verification protocol', effectively isolating "
        "the complainant from outside contact during the extortion. I was "
        "contacted from {phone} claiming to be from the "
        "{impersonated_authority}.",

        "{victim_name} was told that stepping away from the call, even "
        "briefly, would be treated as an admission of guilt and would "
        "trigger immediate arrest. The number that called me was {phone}.",
    ],
    "extortion": [
        "Under continued threat, {victim_name} was instructed to transfer "
        "Rs. {amount} to account {account_ref}, described by the caller as "
        "a 'refundable security deposit' pending verification. Confirmation "
        "of payment was to be sent to {phone}.",

        "{victim_name} was told to deposit Rs. {amount} into account "
        "{account_ref} as an 'RBI compliance fine', with an assurance that "
        "the amount would be returned after the investigation concluded.",

        "The caller directed {victim_name} to transfer Rs. {amount} to "
        "account {account_ref} under the pretext of an 'escrow' arrangement "
        "supposedly monitored by the {impersonated_authority}.",

        "{victim_name} transferred Rs. {amount} to account {account_ref} "
        "after being convinced that the payment was a temporary hold "
        "required to clear the complainant's name in the case. A screenshot "
        "of the transfer was demanded to be sent to {phone}.",

        "Believing the threat to be genuine, {victim_name} sent Rs. "
        "{amount} to account {account_ref}, an amount described by the "
        "caller as a mandatory 'processing fee' for case closure.",
    ],
}

# Simpler lure -> escalating deposit -> lockout structure for the three
# non-digital-arrest subtypes.
SIMPLE_SUBTYPE_TEMPLATES = {
    "investment_app": {
        "lure": [
            "{victim_name} was added to a WhatsApp group promoting a "
            "stock-trading application that promised guaranteed daily "
            "returns, and was encouraged to start with a small trial "
            "investment. The group was managed by an administrator "
            "reachable at {phone}.",

            "An online advertisement led {victim_name} to download an "
            "investment application claiming affiliation with a "
            "well-known trading platform, after which a self-described "
            "'relationship manager' began contacting the complainant "
            "directly, introducing himself over a call from {phone}.",

            "{victim_name}, based in {location}, was approached on social "
            "media by an individual offering access to a private trading "
            "group with claimed weekly returns of ten to fifteen percent.",

            "The complainant {victim_name} was introduced to the scheme "
            "through a friend's referral link and was shown screenshots of "
            "large profits allegedly earned by other members of the group.",

            "{victim_name} received repeated calls from a self-described "
            "'investment advisor' who persuaded the complainant to install "
            "a trading application obtained outside the official app "
            "stores. These calls came from the number {phone}.",
        ],
        "deposit": [
            "{victim_name} initially deposited a small amount and was shown "
            "fabricated profits on the application's dashboard, which "
            "encouraged further transfers of Rs. {amount} to account "
            "{account_ref}.",

            "Encouraged by the visible but fictitious returns, "
            "{victim_name} transferred a further Rs. {amount} to account "
            "{account_ref} to 'unlock' a higher investment tier, after a "
            "follow-up call from {phone} confirming the offer.",

            "{victim_name} was told that a minimum balance of Rs. "
            "{amount}, sent to account {account_ref}, was required before "
            "the application would permit any withdrawal.",

            "Over several weeks, {victim_name} transferred a cumulative "
            "Rs. {amount} to account {account_ref} on the assurance of "
            "steadily compounding returns, with reassurance calls "
            "periodically received from {phone}.",

            "{victim_name} was persuaded to arrange an additional Rs. "
            "{amount}, transferred to account {account_ref}, after being "
            "shown an urgent 'limited slot' offer inside the application.",
        ],
        "lockout": [
            "When {victim_name} attempted to withdraw the accumulated "
            "balance, the application demanded an additional 'tax' payment "
            "before releasing any funds.",

            "{victim_name}'s withdrawal requests were repeatedly rejected "
            "with vague error messages, and the assigned relationship "
            "manager subsequently stopped responding, including on the "
            "number {phone} previously used to contact {victim_name}.",

            "Shortly after the final transfer, the application became "
            "inaccessible and the support number, {phone}, previously used "
            "by {victim_name}, was found to be disconnected.",

            "{victim_name} discovered that the trading dashboard showed "
            "unrealistic gains that could not be withdrawn, at which point "
            "all communication from the platform's representatives ceased.",

            "The application was removed from circulation entirely, and "
            "{victim_name} was unable to recover any of the amounts "
            "transferred, nor reach anyone at the previously used number "
            "{phone}.",
        ],
    },
    "task_based": {
        "lure": [
            "{victim_name} received a message on a messaging app offering "
            "paid 'like and subscribe' tasks with daily payouts credited "
            "instantly for the first few assignments, sent from the number "
            "{phone}.",

            "An advertisement promising part-time income for simple online "
            "tasks led {victim_name} to join a task-based earning group.",

            "{victim_name}, then unemployed, was recruited into a "
            "task-completion scheme through a message forwarded by an "
            "acquaintance.",

            "The complainant {victim_name} was invited to a group offering "
            "'app rating' tasks with an initial payout structure designed "
            "to build trust before larger sums were requested. The group "
            "administrator could be reached at {phone}.",

            "{victim_name} was contacted by a recruiter offering flexible "
            "work-from-home tasks with same-day payment for the earliest "
            "assignments. The recruiter's number was {phone}.",
        ],
        "deposit": [
            "After completing several small paid tasks, {victim_name} was "
            "asked to deposit Rs. {amount} into account {account_ref} to "
            "unlock a 'premium task set' with higher payouts.",

            "{victim_name} was told that a refundable 'registration "
            "deposit' of Rs. {amount}, sent to account {account_ref}, was "
            "required to access higher-value tasks.",

            "The task coordinator instructed {victim_name} to transfer "
            "Rs. {amount} to account {account_ref} to reverse a supposed "
            "negative balance caused by a 'wrongly completed' task, during "
            "a call from {phone}.",

            "{victim_name} made repeated transfers totaling Rs. {amount} "
            "to account {account_ref} in order to remain eligible for the "
            "promised task payouts.",

            "{victim_name} was asked to pay Rs. {amount} to account "
            "{account_ref} as a 'penalty clearance' after being falsely "
            "told that a task deadline had been missed. The demand was "
            "communicated via a call from {phone}.",
        ],
        "lockout": [
            "Despite completing the required deposit, {victim_name} was "
            "unable to withdraw any earnings, and the task-assignment "
            "group was subsequently deleted, along with the contact number "
            "{phone} used throughout.",

            "{victim_name}'s account on the task platform was suddenly "
            "deactivated, with no response from the coordinators who had "
            "previously assigned tasks, including at the number {phone} "
            "previously used to assign tasks.",

            "The withdrawal request placed by {victim_name} remained "
            "pending indefinitely, and further deposits were demanded "
            "before any release of funds.",

            "{victim_name} found that all group administrators had become "
            "unreachable shortly after the final transfer was made, the "
            "last known contact number being {phone}.",

            "The task platform's application was found to be "
            "non-functional, and {victim_name} could no longer access any "
            "record of the completed tasks or promised payouts.",
        ],
    },
    "loan_app": {
        "lure": [
            "{victim_name} downloaded an instant-loan mobile application "
            "after seeing an advertisement promising approval within "
            "minutes without formal documentation.",

            "{victim_name}, facing urgent expenses, applied for a small "
            "personal loan through an unregistered lending application "
            "found via a social media advertisement.",

            "The complainant {victim_name} was approved for a small loan "
            "instantly after granting the application extensive access to "
            "contacts and files on the phone.",

            "{victim_name}, based in {location}, was targeted with "
            "messages offering pre-approved instant loans with minimal "
            "eligibility criteria, sent from the number {phone}.",

            "{victim_name} installed a loan application recommended in a "
            "forwarded message promising same-day disbursal with no "
            "credit check. The message included a contact number, "
            "{phone}, for 'loan queries'.",
        ],
        "deposit": [
            "After disbursing a small loan amount, the application began "
            "demanding Rs. {amount} as a 'processing fee' to account "
            "{account_ref} before releasing the remaining sanctioned "
            "amount, communicated over a call from {phone}.",

            "{victim_name} was asked to pay Rs. {amount} to account "
            "{account_ref} as GST and insurance charges despite these "
            "supposedly already having been deducted from the loan amount, "
            "following a call from {phone} threatening account suspension.",

            "The lender demanded an advance repayment of Rs. {amount} to "
            "account {account_ref}, citing a data-verification error on "
            "{victim_name}'s application.",

            "{victim_name} transferred Rs. {amount} to account "
            "{account_ref} after being threatened with inflated penalty "
            "interest for an alleged missed installment, communicated via "
            "repeated calls from {phone}.",

            "To stop harassment calls, {victim_name} paid an additional "
            "Rs. {amount} to account {account_ref}, described by the "
            "caller as a one-time settlement charge. The calls had been "
            "coming from {phone}.",
        ],
        "lockout": [
            "Despite the payment, {victim_name} continued to receive "
            "harassment calls and threats of morphed-photo circulation to "
            "contacts extracted from the phone, from the number {phone}.",

            "{victim_name}'s loan account balance was found to have "
            "increased rather than decreased after the payment, with no "
            "clear explanation provided.",

            "The loan application became inaccessible shortly after the "
            "payment was made, and the customer support number, {phone}, "
            "was no longer reachable.",

            "{victim_name} discovered that the loan had never been "
            "formally registered with any recognized lending institution, "
            "despite repeated collection calls from {phone}.",

            "Recovery agents continued contacting {victim_name}'s family "
            "members and colleagues despite the demanded payment having "
            "already been made, using the number {phone}.",
        ],
    },
}
