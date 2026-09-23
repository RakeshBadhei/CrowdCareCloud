import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()
from flask import Flask, render_template, request, redirect, session, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from decimal import Decimal, InvalidOperation
import os
import uuid
import smtplib
from email.message import EmailMessage
from db import get_db_connection

app = Flask(__name__)

app.secret_key = "crowdcare-development-secret"

# ================= CREATOR VERIFICATION UPLOADS =================

CREATOR_VERIFICATION_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "uploads",
    "creator_verification"
)

ALLOWED_VERIFICATION_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_VERIFICATION_FILE_SIZE = 5 * 1024 * 1024  # 5 MB per document

os.makedirs(CREATOR_VERIFICATION_FOLDER, exist_ok=True)


# ================= EMAIL NOTIFICATIONS =================
#
# Configure these as environment variables. Do NOT put your real
# email password directly in app.py.
#
# Gmail example:
#   MAIL_HOST=smtp.gmail.com
#   MAIL_PORT=587
#   MAIL_USERNAME=yourcrowdcare@gmail.com
#   MAIL_PASSWORD=your-gmail-app-password
#   MAIL_FROM=yourcrowdcare@gmail.com
#
# For Gmail, MAIL_PASSWORD should be a Google App Password,
# not the normal Gmail account password.

MAIL_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
MAIL_PORT = int(os.getenv("SMTP_PORT", "587"))
MAIL_USERNAME = os.getenv("SMTP_USERNAME", "")
MAIL_PASSWORD = os.getenv("SMTP_PASSWORD", "")
MAIL_FROM = os.getenv("SMTP_FROM", MAIL_USERNAME)

# ================= EMAIL OTP =================
# Development/demo OTP. Every registration/login email verification
# uses this same 4-digit OTP for now.
DEMO_EMAIL_OTP = "6969"


def send_otp_email(to_email, full_name):
    """Send the fixed development OTP to the registered email."""

    if not MAIL_USERNAME or not MAIL_PASSWORD or not MAIL_FROM:
        print(
            f"[OTP] Email notification skipped for {to_email}: "
            """SMTP mail settings are not configured. Use demo OTP 6969."""
        )
        return False

    if not to_email:
        print("[OTP] Email notification skipped: registered email is missing.")
        return False

    message = EmailMessage()
    message["Subject"] = "Your CrowdCare Email Verification OTP"
    message["From"] = MAIL_FROM
    message["To"] = to_email

    message.set_content(
        f"""Hello {full_name},

"""
        f"Your CrowdCare email verification OTP is: {DEMO_EMAIL_OTP}\n\n"
        "Enter this 4-digit OTP on CrowdCare to verify your email address.\n\n"
        "This is the current development/demo OTP used by CrowdCare.\n\n"
        "Regards,\nCrowdCare Cloud"
    )

    try:
        with smtplib.SMTP(MAIL_HOST, MAIL_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(message)

        print(f"[OTP] Verification OTP sent successfully to {to_email}")
        return True

    except Exception as email_error:
        print(
            f"[OTP] Failed to send OTP to {to_email}: {email_error}"
        )
        return False


def send_creator_email(to_email, creator_name, subject, body):
    """
    Send a creator notification email.

    Returns:
        True  -> email sent
        False -> email could not be sent / mail is not configured

    A mail failure never reverses an already completed database decision.
    """

    if not MAIL_USERNAME or not MAIL_PASSWORD or not MAIL_FROM:
        print(
            "[EMAIL] Email notification skipped: "
            "MAIL_USERNAME, MAIL_PASSWORD and MAIL_FROM are not configured."
        )
        return False

    if not to_email:
        print("[EMAIL] Email notification skipped: creator email is missing.")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = MAIL_FROM
    message["To"] = to_email

    message.set_content(body)

    try:
        with smtplib.SMTP(MAIL_HOST, MAIL_PORT, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(message)

        print(f"[EMAIL] Notification sent successfully to {to_email}")
        return True

    except Exception as email_error:
        print(
            f"[EMAIL] Failed to send notification to {to_email}: "
            f"{email_error}"
        )
        return False


def allowed_verification_file(filename):
    return (
        filename
        and "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_VERIFICATION_EXTENSIONS
    )


def save_verification_document(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("A document is required.")

    if not allowed_verification_file(file_storage.filename):
        raise ValueError("Only PDF, PNG, JPG, and JPEG files are allowed.")

    file_storage.stream.seek(0, os.SEEK_END)
    file_size = file_storage.stream.tell()
    file_storage.stream.seek(0)

    if file_size > MAX_VERIFICATION_FILE_SIZE:
        raise ValueError("Each document must be 5 MB or smaller.")

    original_name = secure_filename(file_storage.filename)
    extension = original_name.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{extension}"
    stored_path = os.path.join(CREATOR_VERIFICATION_FOLDER, stored_name)

    file_storage.save(stored_path)

    return stored_path


# ================= HOME =================

@app.route("/")
def home():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Live platform statistics.
        cursor.execute("""
            SELECT
                COALESCE((
                    SELECT SUM(amount)
                    FROM donations
                    WHERE status = 'COMPLETED'
                ), 0) AS total_raised,

                COALESCE((
                    SELECT COUNT(*)
                    FROM campaigns c_public
                    JOIN creators cr_public
                        ON c_public.creator_id = cr_public.creator_id
                    JOIN users u_public
                        ON cr_public.user_id = u_public.user_id
                    WHERE c_public.status IN ('APPROVED', 'ACTIVE', 'COMPLETED')
                      AND u_public.status = 'ACTIVE'
                ), 0) AS campaign_count,

                COALESCE((
                    SELECT COUNT(DISTINCT donor_id)
                    FROM donations
                    WHERE status = 'COMPLETED'
                ), 0) AS donor_count,

                COALESCE((
                    SELECT COUNT(DISTINCT campaign_id)
                    FROM donations
                    WHERE status = 'COMPLETED'
                ), 0) AS campaigns_supported
        """)

        stats = cursor.fetchone()

        # Featured logic:
        # Show the top 3 currently fundable, admin-approved campaigns,
        # ordered by funding progress. Completed/rejected/pending campaigns
        # never appear on the public home page.
        cursor.execute("""
            SELECT
                c.campaign_id,
                c.title,
                c.description,
                c.target_amount,
                c.raised_amount,
                c.cover_image,
                c.city,
                c.status,
                cat.category_name,
                CASE
                    WHEN c.target_amount > 0
                    THEN (c.raised_amount / c.target_amount) * 100
                    ELSE 0
                END AS progress_percent,
                (
                    SELECT COUNT(DISTINCT d.donor_id)
                    FROM donations d
                    WHERE d.campaign_id = c.campaign_id
                      AND d.status = 'COMPLETED'
                ) AS supporter_count,
                CASE
                    WHEN c.end_date IS NULL THEN NULL
                    ELSE GREATEST(DATEDIFF(c.end_date, CURDATE()), 0)
                END AS days_left
            FROM campaigns c
            JOIN creators cr
                ON c.creator_id = cr.creator_id
            JOIN users u
                ON cr.user_id = u.user_id
            LEFT JOIN categories cat
                ON c.category_id = cat.category_id
            WHERE c.status IN ('APPROVED', 'ACTIVE')
              AND u.status = 'ACTIVE'
              AND c.raised_amount < c.target_amount
            ORDER BY progress_percent DESC, c.created_at DESC, c.campaign_id DESC
            LIMIT 3
        """)

        featured_campaigns = cursor.fetchall()

        return render_template(
            "index.html",
            stats=stats,
            featured_campaigns=featured_campaigns
        )

    finally:
        cursor.close()
        connection.close()


# ================= REGISTER =================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip()
        phone = request.form.get("phone", "").strip()
        role = request.form["role"].strip()
        password = request.form["password"]

        if role not in ("DONOR", "CREATOR"):
            return "Invalid registration role.", 400

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()

        try:

            cursor.execute(
                """
                INSERT INTO users
                (full_name, email, password, role, phone, creator_approval_status)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    full_name,
                    email,
                    hashed_password,
                    role,
                    phone,
                    "PENDING" if role == "CREATOR" else "APPROVED"
                )
            )

            user_id = cursor.lastrowid

            if role == "DONOR":

                cursor.execute(
                    """
                    INSERT INTO donors (user_id)
                    VALUES (%s)
                    """,
                    (user_id,)
                )

            elif role == "CREATOR":

                cursor.execute(
                    """
                    INSERT INTO creators (user_id)
                    VALUES (%s)
                    """,
                    (user_id,)
                )

            connection.commit()

            # New accounts must verify the registered email first.
            # The current development OTP is always 6969.
            session["otp_user_id"] = user_id
            session["otp_purpose"] = "REGISTRATION"

            # Attempt to send the OTP to the registered email.
            # A mail failure does not block demo verification with 6969.
            send_otp_email(email, full_name)

            return redirect(url_for("verify_email"))

        except Exception as e:

            connection.rollback()

            return f"Registration failed: {e}"

        finally:

            cursor.close()
            connection.close()

    return render_template("auth/register.html")



# ================= CREATOR VERIFICATION =================

@app.route("/creator-verification", methods=["GET", "POST"])
def creator_verification():

    user_id = session.get("creator_verification_user_id")

    if not user_id:
        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.email,
                u.phone,
                u.role,
                u.creator_approval_status,
                cv.verification_id,
                cv.organization_name,
                cv.ngo_registration_number,
                cv.ngo_email,
                cv.location,
                cv.registration_certificate,
                cv.pan_document,
                cv.representative_id_document,
                cv.bank_proof,
                cv.status AS verification_status,
                cv.rejection_reason
            FROM users u
            LEFT JOIN creator_verifications cv
                ON cv.user_id = u.user_id
            WHERE u.user_id = %s
              AND u.role = 'CREATOR'
        """, (user_id,))

        creator = cursor.fetchone()

        if not creator:
            session.pop("creator_verification_user_id", None)
            return "Creator verification record not found.", 404

        # An already approved creator must NEVER be shown the verification
        # form again, even if an old/stale verification session exists.
        if (
            creator["creator_approval_status"] == "APPROVED"
            or creator["verification_status"] == "APPROVED"
        ):
            # Keep both approval sources consistent for older accounts.
            if creator["creator_approval_status"] != "APPROVED":
                cursor.execute("""
                    UPDATE users
                    SET creator_approval_status = 'APPROVED'
                    WHERE user_id = %s
                      AND role = 'CREATOR'
                """, (creator["user_id"],))
                connection.commit()

            session.pop("creator_verification_user_id", None)

            # If the creator was already authenticated, go straight to dashboard.
            if session.get("user_id") == creator["user_id"]:
                return redirect(url_for("dashboard"))

            return redirect(url_for("login"))

        if request.method == "POST":

            organization_name = request.form.get("organization_name", "").strip()
            ngo_registration_number = request.form.get(
                "ngo_registration_number", ""
            ).strip()
            ngo_email = request.form.get("ngo_email", "").strip()
            location = request.form.get("location", "").strip()

            if not organization_name:
                return "NGO / Organization name is required.", 400

            if not ngo_registration_number:
                return "NGO Registration ID is required.", 400

            if not ngo_email or "@" not in ngo_email:
                return "A valid NGO email is required.", 400

            if not location:
                return "Location is required.", 400

            documents = {
                "registration_certificate": request.files.get(
                    "registration_certificate"
                ),
                "pan_document": request.files.get("pan_document"),
                "representative_id_document": request.files.get(
                    "representative_id_document"
                ),
                "bank_proof": request.files.get("bank_proof")
            }

            saved_paths = {}

            try:
                for field_name, existing_path in (
                    ("registration_certificate", creator["registration_certificate"]),
                    ("pan_document", creator["pan_document"]),
                    ("representative_id_document", creator["representative_id_document"]),
                    ("bank_proof", creator["bank_proof"])
                ):
                    uploaded = documents[field_name]

                    if uploaded and uploaded.filename:
                        saved_paths[field_name] = save_verification_document(
                            uploaded
                        )
                    elif existing_path:
                        saved_paths[field_name] = existing_path
                    else:
                        raise ValueError(
                            f"{field_name.replace('_', ' ').title()} is required."
                        )

            except ValueError as e:
                for path in saved_paths.values():
                    if path and path not in (
                        creator["registration_certificate"],
                        creator["pan_document"],
                        creator["representative_id_document"],
                        creator["bank_proof"]
                    ):
                        if os.path.exists(path):
                            os.remove(path)
                return str(e), 400

            verification_values = (
                organization_name,
                ngo_registration_number,
                ngo_email,
                location,
                saved_paths["registration_certificate"],
                saved_paths["pan_document"],
                saved_paths["representative_id_document"],
                saved_paths["bank_proof"]
            )

            if creator["verification_id"]:
                cursor.execute("""
                    UPDATE creator_verifications
                    SET
                        organization_name = %s,
                        ngo_registration_number = %s,
                        ngo_email = %s,
                        location = %s,
                        registration_certificate = %s,
                        pan_document = %s,
                        representative_id_document = %s,
                        bank_proof = %s,
                        status = 'PENDING',
                        rejection_reason = NULL,
                        reviewed_at = NULL,
                        reviewed_by = NULL,
                        submitted_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                """, verification_values + (user_id,))
            else:
                cursor.execute("""
                    INSERT INTO creator_verifications
                    (
                        user_id,
                        organization_name,
                        ngo_registration_number,
                        ngo_email,
                        location,
                        registration_certificate,
                        pan_document,
                        representative_id_document,
                        bank_proof,
                        status,
                        submitted_at
                    )
                    VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'PENDING', CURRENT_TIMESTAMP)
                """, (user_id,) + verification_values)

            cursor.execute("""
                UPDATE users
                SET creator_approval_status = 'PENDING'
                WHERE user_id = %s
                  AND role = 'CREATOR'
            """, (user_id,))

            connection.commit()

            session.pop("creator_verification_user_id", None)

            return redirect("/login")

        return render_template(
            "creator_verification.html",
            creator=creator
        )

    finally:
        cursor.close()
        connection.close()


# ================= LOGIN =================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        connection = get_db_connection()

        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                u.*,
                cv.status AS verification_status
            FROM users u
            LEFT JOIN creator_verifications cv
                ON cv.user_id = u.user_id
            WHERE u.email = %s
        """,
            (email,)
        )

        user = cursor.fetchone()

        cursor.close()
        connection.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            # Only ACTIVE accounts can log in.
            if user["status"] != "ACTIVE":
                return "Your account is currently INACTIVE or BLOCKED. Please contact an administrator.", 403

            # EVERY account must complete email OTP verification on EVERY login.
            # This applies to ADMIN, DONOR, and CREATOR accounts.
            # The development/demo OTP is always 6969.
            session["otp_user_id"] = user["user_id"]
            session["otp_purpose"] = "LOGIN"
            send_otp_email(user["email"], user["full_name"])
            return redirect(url_for("verify_email"))

            # Creator approval is checked only after email OTP verification.
            if user["role"] == "CREATOR":

                # If the verification record is already APPROVED but the
                # user-level status is stale, synchronize it automatically.
                if (
                    user.get("creator_approval_status") != "APPROVED"
                    and user.get("verification_status") == "APPROVED"
                ):
                    sync_connection = get_db_connection()
                    sync_cursor = sync_connection.cursor()
                    try:
                        sync_cursor.execute("""
                            UPDATE users
                            SET creator_approval_status = 'APPROVED'
                            WHERE user_id = %s
                              AND role = 'CREATOR'
                        """, (user["user_id"],))
                        sync_connection.commit()
                        user["creator_approval_status"] = "APPROVED"
                    finally:
                        sync_cursor.close()
                        sync_connection.close()

                if user["creator_approval_status"] != "APPROVED":
                    if user["creator_approval_status"] == "PENDING":
                        return "Your creator account is awaiting admin approval.", 403

                    # A rejected creator may authenticate and resubmit
                    # the verification documents, but cannot enter the dashboard.
                    session["creator_verification_user_id"] = user["user_id"]
                    return redirect(url_for("creator_verification"))

            session["user_id"] = user["user_id"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]

            return redirect("/dashboard")

        return "Invalid email or password."

    return render_template("auth/login.html")

# ================= EMAIL OTP VERIFICATION =================

@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():

    user_id = session.get("otp_user_id")

    if not user_id:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                user_id,
                full_name,
                email,
                role,
                email_verified
            FROM users
            WHERE user_id = %s
        """, (user_id,))

        user = cursor.fetchone()

        if not user:
            session.pop("otp_user_id", None)
            session.pop("otp_purpose", None)
            return "User not found.", 404

        # OTP is required for every login, even if this email was verified
        # during an earlier login. The email_verified field records that the
        # address has been verified before; it does not bypass login OTP.
        if request.method == "POST":
            otp = request.form.get("otp", "").strip()

            if len(otp) != 4 or not otp.isdigit():
                return "Enter the 4-digit OTP.", 400

            if otp != DEMO_EMAIL_OTP:
                return "Invalid OTP. Please enter the 4-digit OTP sent to your registered email.", 400

            cursor.execute("""
                UPDATE users
                SET email_verified = 1
                WHERE user_id = %s
            """, (user_id,))

            connection.commit()

            purpose = session.get("otp_purpose")
            session.pop("otp_user_id", None)
            session.pop("otp_purpose", None)

            if purpose == "REGISTRATION" and user["role"] == "CREATOR":
                session["creator_verification_user_id"] = user_id
                return redirect(url_for("creator_verification"))

            if purpose == "REGISTRATION":
                return redirect(url_for("login"))

            # LOGIN OTP: establish the normal authenticated session.
            session["user_id"] = user["user_id"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]

            if user["role"] == "CREATOR":
                cursor.execute("""
                    SELECT creator_approval_status
                    FROM users
                    WHERE user_id = %s
                """, (user_id,))

                approval = cursor.fetchone()

                if approval and approval["creator_approval_status"] != "APPROVED":
                    if approval["creator_approval_status"] == "PENDING":
                        session.pop("user_id", None)
                        session.pop("full_name", None)
                        session.pop("role", None)
                        return "Your creator account is awaiting admin approval.", 403

                    session.pop("creator_verification_user_id", None)
                    session.pop("user_id", None)
                    session.pop("full_name", None)
                    session.pop("role", None)
                    session["creator_verification_user_id"] = user_id
                    return redirect(url_for("creator_verification"))

            return redirect(url_for("dashboard"))

        return render_template(
            "auth/verify_email.html",
            user=user,
            demo_otp=DEMO_EMAIL_OTP
        )

    finally:
        cursor.close()
        connection.close()


@app.route("/resend-email-otp", methods=["POST"])
def resend_email_otp():

    user_id = session.get("otp_user_id")

    if not user_id:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT full_name, email
            FROM users
            WHERE user_id = %s
        """, (user_id,))

        user = cursor.fetchone()

        if not user:
            session.pop("otp_user_id", None)
            session.pop("otp_purpose", None)
            return redirect(url_for("login"))

        send_otp_email(user["email"], user["full_name"])
        return redirect(url_for("verify_email"))

    finally:
        cursor.close()
        connection.close()


@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                user_id,
                full_name,
                role,
                status,
                creator_approval_status
            FROM users
            WHERE user_id = %s
        """, (session["user_id"],))

        user = cursor.fetchone()

        if not user:
            session.clear()
            return redirect("/login")

        # Re-check account status so an already logged-in user cannot
        # continue using the account after an administrator disables it.
        if user["status"] != "ACTIVE":
            session.clear()
            return "Your account is currently INACTIVE or BLOCKED. Please contact an administrator.", 403

        # Re-check creator approval for an existing creator session.
        if user["role"] == "CREATOR" and user["creator_approval_status"] != "APPROVED":
            session.clear()
            if user["creator_approval_status"] == "PENDING":
                return "Your creator account is awaiting admin approval.", 403
            return "Your creator account has been rejected by an administrator.", 403

        # Keep the session synchronized with the current database role/name.
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]

        creator_bank_account = None

        if user["role"] == "CREATOR":
            cursor.execute("""
                SELECT
                    bank_account_id,
                    account_holder_name,
                    bank_name,
                    account_number,
                    ifsc_code,
                    status,
                    created_at,
                    updated_at
                FROM creator_bank_accounts
                WHERE creator_id = (
                    SELECT creator_id
                    FROM creators
                    WHERE user_id = %s
                )
                LIMIT 1
            """, (session["user_id"],))

            creator_bank_account = cursor.fetchone()

        return render_template(
            "dashboard.html",
            full_name=user["full_name"],
            role=user["role"],
            creator_bank_account=creator_bank_account
        )

    finally:
        cursor.close()
        connection.close()
# ================= CREATOR BANK ACCOUNT =================

@app.route("/creator/bank-account", methods=["GET", "POST"])
def creator_bank_account():

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "CREATOR":
        return "Only creators can manage a bank account.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.status,
                u.creator_approval_status,
                cr.creator_id
            FROM users u
            JOIN creators cr
                ON cr.user_id = u.user_id
            WHERE u.user_id = %s
              AND u.role = 'CREATOR'
        """, (session["user_id"],))

        creator = cursor.fetchone()

        if not creator:
            return "Creator profile not found.", 404

        if creator["status"] != "ACTIVE":
            return "Your creator account is not active.", 403

        if creator["creator_approval_status"] != "APPROVED":
            return "Your creator account must be approved before registering a bank account.", 403

        cursor.execute("""
            SELECT
                bank_account_id,
                account_holder_name,
                bank_name,
                account_number,
                ifsc_code,
                status,
                created_at,
                updated_at
            FROM creator_bank_accounts
            WHERE creator_id = %s
            LIMIT 1
        """, (creator["creator_id"],))

        bank_account = cursor.fetchone()

        if request.method == "POST":
            account_holder_name = request.form.get("account_holder_name", "").strip()
            bank_name = request.form.get("bank_name", "").strip()
            account_number = request.form.get("account_number", "").strip()
            confirm_account_number = request.form.get("confirm_account_number", "").strip()
            ifsc_code = request.form.get("ifsc_code", "").strip().upper()

            if not account_holder_name:
                return "Account holder name is required.", 400

            if not bank_name:
                return "Bank name is required.", 400

            if not account_number.isdigit() or not (9 <= len(account_number) <= 18):
                return "Enter a valid bank account number.", 400

            if account_number != confirm_account_number:
                return "Bank account numbers do not match.", 400

            if len(ifsc_code) != 11 or not ifsc_code[:4].isalpha() or ifsc_code[4] != "0" or not ifsc_code[5:].isalnum():
                return "Enter a valid 11-character IFSC code.", 400

            if bank_account:
                cursor.execute("""
                    UPDATE creator_bank_accounts
                    SET
                        account_holder_name = %s,
                        bank_name = %s,
                        account_number = %s,
                        ifsc_code = %s,
                        status = 'ACTIVE',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE creator_id = %s
                """, (
                    account_holder_name,
                    bank_name,
                    account_number,
                    ifsc_code,
                    creator["creator_id"]
                ))
            else:
                cursor.execute("""
                    INSERT INTO creator_bank_accounts
                    (
                        creator_id,
                        account_holder_name,
                        bank_name,
                        account_number,
                        ifsc_code,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s, 'ACTIVE')
                """, (
                    creator["creator_id"],
                    account_holder_name,
                    bank_name,
                    account_number,
                    ifsc_code
                ))

            connection.commit()
            return redirect(url_for("creator_bank_account"))

        return render_template(
            "creator_bank_account.html",
            creator=creator,
            bank_account=bank_account
        )

    except Exception as e:
        connection.rollback()
        return f"Bank account operation failed: {e}", 500

    finally:
        cursor.close()
        connection.close()


# ================= CATEGORIES =================

@app.route("/categories")
def categories():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                category_id,
                category_name
            FROM categories
            ORDER BY category_name
        """)

        categories = cursor.fetchall()

        return render_template(
            "categories.html",
            categories=categories
        )

    finally:
        cursor.close()
        connection.close()
        # ================= CATEGORY CAMPAIGNS =================

@app.route("/category/<int:category_id>")
def category_campaigns(category_id):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Get category
        cursor.execute("""
            SELECT category_id, category_name
            FROM categories
            WHERE category_id = %s
        """, (category_id,))

        category = cursor.fetchone()

        if not category:
            return "Category not found.", 404

        # Get ONLY campaigns from this category
        cursor.execute("""
            SELECT
                c.campaign_id,
                c.title,
                c.description,
                c.target_amount,
                c.raised_amount,
                c.cover_image,
                c.city,
                c.start_date,
                c.end_date,
                c.status,
                cat.category_name
            FROM campaigns c
            JOIN creators cr
                ON c.creator_id = cr.creator_id
            JOIN users u
                ON cr.user_id = u.user_id
            LEFT JOIN categories cat
                ON c.category_id = cat.category_id
            WHERE c.category_id = %s
              AND c.status = 'APPROVED'
              AND u.status = 'ACTIVE'
              AND c.raised_amount < c.target_amount
            ORDER BY c.campaign_id DESC
        """, (category_id,))

        campaigns = cursor.fetchall()

        return render_template(
            "category_campaigns.html",
            category=category,
            campaigns=campaigns
        )

    finally:
        cursor.close()
        connection.close()

# ================= CAMPAIGNS =================

@app.route("/campaigns")
def campaigns():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # =====================================================
        # ADMIN → CAN SEE ALL CAMPAIGNS
        # =====================================================

        if session.get("role") == "ADMIN":

            cursor.execute("""
                SELECT
                    c.campaign_id,
                    c.title,
                    c.description,
                    c.target_amount,
                    c.raised_amount,
                    c.cover_image,
                    c.city,
                    c.start_date,
                    c.end_date,
                    c.status,
                    cat.category_name
                FROM campaigns c
                LEFT JOIN categories cat
                    ON c.category_id = cat.category_id
                ORDER BY c.campaign_id DESC
            """)

        # =====================================================
        # NORMAL USERS / DONORS / CREATORS
        # → ONLY APPROVED CAMPAIGNS
        # =====================================================

        else:

            cursor.execute("""
                SELECT
                    c.campaign_id,
                    c.title,
                    c.description,
                    c.target_amount,
                    c.raised_amount,
                    c.cover_image,
                    c.city,
                    c.start_date,
                    c.end_date,
                    c.status,
                    cat.category_name
                FROM campaigns c
                JOIN creators cr
                    ON c.creator_id = cr.creator_id
                JOIN users u
                    ON cr.user_id = u.user_id
                LEFT JOIN categories cat
                    ON c.category_id = cat.category_id
                WHERE c.status = 'APPROVED'
                  AND u.status = 'ACTIVE'
                  AND c.raised_amount < c.target_amount
                ORDER BY c.campaign_id DESC
            """)

        campaigns = cursor.fetchall()

        return render_template(
            "campaigns.html",
            campaigns=campaigns
        )

    finally:

        cursor.close()
        connection.close()
# ================= CAMPAIGN DETAILS =================

@app.route("/campaign/<int:campaign_id>")
def campaign_details(campaign_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                c.campaign_id,
                c.title,
                c.description,
                c.target_amount,
                c.raised_amount,
                c.cover_image,
                c.city,
                c.start_date,
                c.end_date,
                c.status,
                c.rejection_reason,
                c.closure_reason,
                c.closed_at,
                c.closed_by,
                cat.category_name,
                cr.creator_id AS creator_id,
                u.full_name AS creator_name
            FROM campaigns c
            LEFT JOIN categories cat
                ON c.category_id = cat.category_id
            LEFT JOIN creators cr
                ON c.creator_id = cr.creator_id
            LEFT JOIN users u
                ON cr.user_id = u.user_id
            WHERE c.campaign_id = %s
        """, (campaign_id,))

        campaign = cursor.fetchone()

        if not campaign:
            return "Campaign not found.", 404

        # Public users can only view campaigns owned by ACTIVE creators.
        # Admins can still inspect campaigns belonging to inactive/blocked creators.
        if session.get("role") != "ADMIN":
            if not campaign.get("creator_id"):
                return "This campaign is not currently available.", 403

            cursor.execute("""
                SELECT u.status
                FROM creators cr
                JOIN users u
                    ON cr.user_id = u.user_id
                WHERE cr.creator_id = %s
            """, (campaign["creator_id"],))

            creator_status = cursor.fetchone()

            if not creator_status or creator_status["status"] != "ACTIVE":
                return "This campaign is not currently available.", 403

        # Public users can view approved/active/completed campaign history.
        # Pending/rejected campaigns remain admin-only.
        if campaign["status"] not in ("APPROVED", "COMPLETED", "ACTIVE"):
            if session.get("role") != "ADMIN":
                return "This campaign is not currently available.", 403

        # Admin campaign safety / refund information.
        donation_count = 0
        completed_donation_total = Decimal("0.00")
        completed_withdrawal_amount = Decimal("0.00")

        cursor.execute("""
            SELECT
                COUNT(*) AS donation_count,
                COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN amount ELSE 0 END), 0) AS completed_donation_total,
                COALESCE(SUM(CASE WHEN status = 'REFUNDED' THEN amount ELSE 0 END), 0) AS refunded_donation_total
            FROM donations
            WHERE campaign_id = %s
        """, (campaign_id,))

        donation_summary = cursor.fetchone()
        donation_count = int(donation_summary["donation_count"] or 0)
        completed_donation_total = Decimal(str(donation_summary["completed_donation_total"] or 0))

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS completed_withdrawal_amount
            FROM creator_withdrawals
            WHERE campaign_id = %s
              AND status = 'COMPLETED'
        """, (campaign_id,))

        withdrawal_summary = cursor.fetchone()
        completed_withdrawal_amount = Decimal(
            str(withdrawal_summary["completed_withdrawal_amount"] or 0)
        )

        campaign_withdrawals = []
        campaign_withdrawable = Decimal("0.00")
        creator_owns_campaign = False
        creator_bank_account = None

        if session.get("role") == "CREATOR":
            cursor.execute("""
                SELECT cr.creator_id
                FROM creators cr
                WHERE cr.user_id = %s
            """, (session["user_id"],))

            creator_row = cursor.fetchone()

            if creator_row and creator_row["creator_id"] == campaign["creator_id"]:
                creator_owns_campaign = True

                cursor.execute("""
                    SELECT
                        bank_account_id,
                        account_holder_name,
                        bank_name,
                        account_number,
                        ifsc_code,
                        status
                    FROM creator_bank_accounts
                    WHERE creator_id = %s
                    LIMIT 1
                """, (creator_row["creator_id"],))

                creator_bank_account = cursor.fetchone()

                cursor.execute("""
                    SELECT
                        w.withdrawal_id,
                        w.amount,
                        w.status,
                        w.rejection_reason,
                        w.requested_at,
                        w.reviewed_at,
                        reviewer.full_name AS reviewer_name
                    FROM creator_withdrawals w
                    LEFT JOIN users reviewer
                        ON reviewer.user_id = w.reviewed_by
                    WHERE w.campaign_id = %s
                      AND w.creator_id = %s
                    ORDER BY w.withdrawal_id DESC
                """, (campaign_id, creator_row["creator_id"]))

                campaign_withdrawals = cursor.fetchall()

                cursor.execute("""
                    SELECT COALESCE(SUM(amount), 0) AS reserved_amount
                    FROM creator_withdrawals
                    WHERE campaign_id = %s
                      AND creator_id = %s
                      AND status IN ('PENDING', 'APPROVED', 'COMPLETED')
                """, (campaign_id, creator_row["creator_id"]))

                reserved_row = cursor.fetchone()
                reserved_amount = Decimal(str(reserved_row["reserved_amount"] or 0))
                raised_amount = Decimal(str(campaign["raised_amount"] or 0))
                campaign_withdrawable = max(Decimal("0.00"), raised_amount - reserved_amount)

        return render_template(
            "campaign_details.html",
            campaign=campaign,
            campaign_withdrawals=campaign_withdrawals,
            campaign_withdrawable=campaign_withdrawable,
            creator_owns_campaign=creator_owns_campaign,
            creator_bank_account=creator_bank_account,
            donation_count=donation_count,
            completed_donation_total=completed_donation_total,
            completed_withdrawal_amount=completed_withdrawal_amount
        )

    finally:
        cursor.close()
        connection.close()

    # ================= CREATOR PROFILE =================

@app.route("/creator/<int:creator_id>")
def creator_profile(creator_id):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Get the creator's basic account information.
        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.status,
                u.creator_approval_status,
                u.created_at,
                cr.creator_id
            FROM creators cr
            JOIN users u
                ON cr.user_id = u.user_id
            WHERE cr.creator_id = %s
        """, (creator_id,))

        creator = cursor.fetchone()

        if not creator:
            return "Creator not found.", 404

        # Public creator profiles are available only for ACTIVE accounts.
        # Admins can still inspect inactive/blocked creators.
        if session.get("role") != "ADMIN" and creator["status"] != "ACTIVE":
            return "Creator not found.", 404

        # Campaign statistics.
        cursor.execute("""
            SELECT
                COUNT(*) AS total_campaigns,
                SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending_campaigns,
                SUM(CASE WHEN status IN ('APPROVED', 'ACTIVE') THEN 1 ELSE 0 END) AS approved_campaigns,
                SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) AS rejected_campaigns,
                SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_campaigns,
                SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END) AS closed_campaigns,
                COALESCE(
                    SUM(
                        CASE
                            WHEN status IN ('APPROVED', 'ACTIVE', 'COMPLETED')
                            THEN raised_amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS total_raised
            FROM campaigns
            WHERE creator_id = %s
        """, (creator_id,))

        stats = cursor.fetchone()

        # A normal creator account does not have a donor profile because
        # users.role is a single role. This query still supports the case
        # where a donor row exists for the same user.
        cursor.execute("""
            SELECT
                COUNT(d.donation_id) AS donation_count,
                COALESCE(SUM(
                    CASE
                        WHEN d.status = 'COMPLETED' THEN d.amount
                        ELSE 0
                    END
                ), 0) AS total_donated
            FROM users u
            LEFT JOIN donors dr
                ON dr.user_id = u.user_id
            LEFT JOIN donations d
                ON d.donor_id = dr.donor_id
            WHERE u.user_id = %s
        """, (creator["user_id"],))

        donation_stats = cursor.fetchone()

        # Admins can inspect all campaigns belonging to the creator.
        # Normal users only see campaigns that are publicly available/history.
        if session.get("role") == "ADMIN":
            cursor.execute("""
                SELECT
                    c.campaign_id,
                    c.title,
                    c.description,
                    c.target_amount,
                    c.raised_amount,
                    c.city,
                    c.start_date,
                    c.end_date,
                    c.status,
                    c.rejection_reason,
                    cat.category_name
                FROM campaigns c
                LEFT JOIN categories cat
                    ON c.category_id = cat.category_id
                WHERE c.creator_id = %s
                ORDER BY c.created_at DESC, c.campaign_id DESC
            """, (creator_id,))
        else:
            cursor.execute("""
                SELECT
                    c.campaign_id,
                    c.title,
                    c.description,
                    c.target_amount,
                    c.raised_amount,
                    c.city,
                    c.start_date,
                    c.end_date,
                    c.status,
                    c.rejection_reason,
                    cat.category_name
                FROM campaigns c
                JOIN creators cr
                    ON c.creator_id = cr.creator_id
                JOIN users u
                    ON cr.user_id = u.user_id
                LEFT JOIN categories cat
                    ON c.category_id = cat.category_id
                WHERE c.creator_id = %s
                  AND u.status = 'ACTIVE'
                  AND c.status IN ('APPROVED', 'ACTIVE', 'COMPLETED')
                ORDER BY c.created_at DESC, c.campaign_id DESC
            """, (creator_id,))

        creator_campaigns = cursor.fetchall()

        return render_template(
            "creator_profile.html",
            creator=creator,
            stats=stats,
            donation_stats=donation_stats,
            creator_campaigns=creator_campaigns,
            is_admin=(session.get("role") == "ADMIN")
        )

    finally:
        cursor.close()
        connection.close()


    # ================= DONATE =================

@app.route("/donate/<int:campaign_id>", methods=["GET", "POST"])
def donate(campaign_id):

    # User must be logged in.
    if "user_id" not in session:
        return redirect("/login")

    # Only donors can donate.
    if session.get("role") != "DONOR":
        return "Only donors can make donations.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT status, role
            FROM users
            WHERE user_id = %s
        """, (session["user_id"],))

        current_user = cursor.fetchone()

        if (
            not current_user
            or current_user["status"] != "ACTIVE"
            or current_user["role"] != "DONOR"
        ):
            session.clear()
            return "Your donor account is not active. Please contact an administrator.", 403

        cursor.execute("""
            SELECT
                campaign_id,
                title,
                target_amount,
                raised_amount,
                status
            FROM campaigns
            WHERE campaign_id = %s
        """, (campaign_id,))

        campaign = cursor.fetchone()

        if not campaign:
            return "Campaign not found.", 404

        # Donations are allowed only for approved campaigns.
        if campaign["status"] != "APPROVED":
            return "This campaign is not currently accepting donations.", 403

        target_amount = Decimal(str(campaign["target_amount"]))
        raised_amount = Decimal(str(campaign["raised_amount"]))

        # Protect against stale campaign data that has already reached its target.
        if raised_amount >= target_amount:
            cursor.execute("""
                UPDATE campaigns
                SET status = 'COMPLETED'
                WHERE campaign_id = %s
            """, (campaign_id,))
            connection.commit()
            return "This campaign has already reached its target and is now completed.", 403

        # Get donor_id belonging to the logged-in user.
        cursor.execute("""
            SELECT donor_id
            FROM donors
            WHERE user_id = %s
        """, (session["user_id"],))

        donor = cursor.fetchone()

        if not donor:
            return "Donor profile not found.", 404

        if request.method == "POST":
            amount_text = request.form.get("amount", "").strip()
            payment_method = request.form.get("payment_method", "").strip()

            # Use Decimal for money values instead of float.
            try:
                amount = Decimal(amount_text)
            except (InvalidOperation, ValueError):
                return "Invalid donation amount.", 400

            # Keep money values to a maximum of two decimal places.
            if amount.as_tuple().exponent < -2:
                return "Donation amount can have a maximum of 2 decimal places.", 400

            if amount <= 0:
                return "Donation amount must be greater than ₹0.", 400

            remaining_amount = target_amount - raised_amount

            # Do not allow a donation to exceed the remaining target.
            if amount > remaining_amount:
                return (
                    f"Donation amount cannot exceed the remaining target of "
                    f"₹{remaining_amount:.2f}.",
                    400
                )

            if payment_method not in ("UPI", "CARD", "NET_BANKING", "WALLET"):
                return "Invalid payment method.", 400

            # Store only the validated payment request temporarily.
            # The donation is NOT recorded until the payment confirmation step.
            session["pending_donation"] = {
                "campaign_id": campaign_id,
                "amount": str(amount.quantize(Decimal("0.01"))),
                "payment_method": payment_method
            }
            session.modified = True

            return redirect(url_for("payment", campaign_id=campaign_id))

        return render_template(
            "donate.html",
            campaign=campaign
        )

    finally:
        cursor.close()
        connection.close()


# ================= PAYMENT CONFIRMATION =================

@app.route("/payment/<int:campaign_id>", methods=["GET", "POST"])
def payment(campaign_id):

    # User must be logged in.
    if "user_id" not in session:
        return redirect("/login")

    # Only donors can complete payments.
    if session.get("role") != "DONOR":
        return "Only donors can make donations.", 403

    pending = session.get("pending_donation")

    # Prevent users from directly opening a payment URL without starting a donation.
    if not pending or pending.get("campaign_id") != campaign_id:
        return redirect(url_for("donate", campaign_id=campaign_id))

    try:
        amount = Decimal(str(pending["amount"]))
    except (InvalidOperation, ValueError):
        session.pop("pending_donation", None)
        return "Invalid pending donation.", 400

    payment_method = pending.get("payment_method")

    if payment_method not in ("UPI", "CARD", "NET_BANKING", "WALLET"):
        session.pop("pending_donation", None)
        return "Invalid payment method.", 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT status, role
            FROM users
            WHERE user_id = %s
        """, (session["user_id"],))

        current_user = cursor.fetchone()

        if (
            not current_user
            or current_user["status"] != "ACTIVE"
            or current_user["role"] != "DONOR"
        ):
            session.pop("pending_donation", None)
            session.clear()
            return "Your donor account is not active. Please contact an administrator.", 403

        # Lock the campaign row so two simultaneous donations cannot
        # push the campaign beyond its target.
        cursor.execute("""
            SELECT
                campaign_id,
                title,
                target_amount,
                raised_amount,
                status
            FROM campaigns
            WHERE campaign_id = %s
            FOR UPDATE
        """, (campaign_id,))

        campaign = cursor.fetchone()

        if not campaign:
            session.pop("pending_donation", None)
            return "Campaign not found.", 404

        if campaign["status"] != "APPROVED":
            session.pop("pending_donation", None)
            return "This campaign is no longer accepting donations.", 403

        target_amount = Decimal(str(campaign["target_amount"]))
        raised_amount = Decimal(str(campaign["raised_amount"]))
        remaining_amount = target_amount - raised_amount

        # Re-check the remaining target at payment time because the campaign
        # may have received another donation while this page was open.
        if amount <= 0 or amount > remaining_amount:
            session.pop("pending_donation", None)

            if remaining_amount <= 0:
                cursor.execute("""
                    UPDATE campaigns
                    SET status = 'COMPLETED'
                    WHERE campaign_id = %s
                """, (campaign_id,))
                connection.commit()
                return "This campaign has already reached its target.", 403

            return (
                f"This donation can no longer be processed because the "
                f"remaining target is ₹{remaining_amount:.2f}.",
                400
            )

        if request.method == "POST":
            try:
                # Demo payment confirmation.
                # A real gateway can replace this confirmation step later.
                # Get donor_id from the authenticated user inside the transaction.
                cursor.execute("""
                    SELECT donor_id
                    FROM donors
                    WHERE user_id = %s
                """, (session["user_id"],))

                donor = cursor.fetchone()

                if not donor:
                    connection.rollback()
                    session.pop("pending_donation", None)
                    return "Donor profile not found.", 404

                cursor.execute("""
                    INSERT INTO donations
                    (
                        campaign_id,
                        donor_id,
                        amount,
                        payment_method,
                        status
                    )
                    VALUES
                    (%s, %s, %s, %s, 'COMPLETED')
                """, (
                    campaign_id,
                    donor["donor_id"],
                    amount,
                    payment_method
                ))

                new_raised_amount = raised_amount + amount

                if new_raised_amount >= target_amount:
                    cursor.execute("""
                        UPDATE campaigns
                        SET raised_amount = %s,
                            status = 'COMPLETED'
                        WHERE campaign_id = %s
                    """, (
                        new_raised_amount,
                        campaign_id
                    ))
                else:
                    cursor.execute("""
                        UPDATE campaigns
                        SET raised_amount = %s
                        WHERE campaign_id = %s
                    """, (
                        new_raised_amount,
                        campaign_id
                    ))

                connection.commit()
                session.pop("pending_donation", None)

                return redirect(url_for("donation_success", campaign_id=campaign_id))

            except Exception as e:
                connection.rollback()
                return f"Payment failed: {e}", 500

        return render_template(
            "payment.html",
            campaign=campaign,
            amount=amount,
            payment_method=payment_method
        )

    finally:
        cursor.close()
        connection.close()


# ================= DONATION SUCCESS =================

@app.route("/donation-success/<int:campaign_id>")
def donation_success(campaign_id):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "DONOR":
        return "Only donors can view donation confirmation.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT status, role
            FROM users
            WHERE user_id = %s
        """, (session["user_id"],))

        current_user = cursor.fetchone()

        if (
            not current_user
            or current_user["status"] != "ACTIVE"
            or current_user["role"] != "DONOR"
        ):
            session.clear()
            return "Your donor account is not active. Please contact an administrator.", 403

        cursor.execute("""
            SELECT
                c.campaign_id,
                c.title,
                c.target_amount,
                c.raised_amount,
                d.donation_id,
                d.amount,
                d.payment_method,
                d.donation_date
            FROM donations d
            JOIN campaigns c
                ON d.campaign_id = c.campaign_id
            JOIN donors dr
                ON d.donor_id = dr.donor_id
            WHERE d.campaign_id = %s
              AND dr.user_id = %s
            ORDER BY d.donation_id DESC
            LIMIT 1
        """, (campaign_id, session["user_id"]))

        donation = cursor.fetchone()

        if not donation:
            return "Donation confirmation not found.", 404

        return render_template(
            "donation_success.html",
            donation=donation
        )

    finally:
        cursor.close()
        connection.close()

    # ================= DONATION HISTORY =================

@app.route("/my-donations")
def my_donations():

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "DONOR":
        return "Only donors can view donation history.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT status, role
            FROM users
            WHERE user_id = %s
        """, (session["user_id"],))

        current_user = cursor.fetchone()

        if (
            not current_user
            or current_user["status"] != "ACTIVE"
            or current_user["role"] != "DONOR"
        ):
            session.clear()
            return "Your donor account is not active. Please contact an administrator.", 403

        cursor.execute("""
            SELECT
                d.donation_id,
                d.campaign_id,
                d.amount,
                d.payment_method,
                d.status,
                d.donation_date,
                c.title AS campaign_title
        FROM donations d
        JOIN donors dr
            ON d.donor_id = dr.donor_id
        JOIN campaigns c
            ON d.campaign_id = c.campaign_id
        WHERE dr.user_id = %s
        ORDER BY d.donation_date DESC
    """, (session["user_id"],))

        donations = cursor.fetchall()

        return render_template(
            "my_donations.html",
            donations=donations
        )

    finally:
        cursor.close()
        connection.close()

# ================= MY CAMPAIGNS =================

@app.route("/my-campaigns")
def my_campaigns():

    if "user_id" not in session:
        return redirect("/login")

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT role, status, creator_approval_status
            FROM users
            WHERE user_id = %s
        """, (session["user_id"],))

        user = cursor.fetchone()

        if not user:
            session.clear()
            return redirect("/login")

        if user["status"] != "ACTIVE":
            session.clear()
            return "Your account is currently INACTIVE or BLOCKED. Please contact an administrator.", 403

        if user["role"] != "CREATOR":
            return "Only creators can view their campaigns.", 403

        if user["creator_approval_status"] != "APPROVED":
            session.clear()
            if user["creator_approval_status"] == "PENDING":
                return "Your creator account is awaiting admin approval.", 403
            return "Your creator account has been rejected by an administrator.", 403

        # Continue with the existing campaign query using this cursor.
        cursor.execute("""
            SELECT
                c.campaign_id,
                c.title,
                c.description,
                c.target_amount,
                c.raised_amount,
                c.city,
                c.start_date,
                c.end_date,
                c.status,
                c.rejection_reason,
                cat.category_name
            FROM campaigns c
            JOIN creators cr
                ON c.creator_id = cr.creator_id
            LEFT JOIN categories cat
                ON c.category_id = cat.category_id
            WHERE cr.user_id = %s
            ORDER BY c.campaign_id DESC
        """, (session["user_id"],))

        campaigns = cursor.fetchall()

        cursor.execute("""
            SELECT
                w.withdrawal_id,
                w.campaign_id,
                w.amount,
                w.status,
                w.rejection_reason,
                w.requested_at,
                w.reviewed_at,
                reviewer.full_name AS reviewer_name
            FROM creator_withdrawals w
            LEFT JOIN users reviewer
                ON reviewer.user_id = w.reviewed_by
            JOIN creators cr
                ON cr.creator_id = w.creator_id
            WHERE cr.user_id = %s
            ORDER BY w.withdrawal_id DESC
        """, (session["user_id"],))

        withdrawal_rows = cursor.fetchall()
        withdrawals_by_campaign = {}

        for withdrawal in withdrawal_rows:
            withdrawals_by_campaign.setdefault(
                withdrawal["campaign_id"], []
            ).append(withdrawal)

        return render_template(
            "my_campaigns.html",
            campaigns=campaigns,
            withdrawals_by_campaign=withdrawals_by_campaign
        )

    finally:
        cursor.close()
        connection.close()
# ================= CAMPAIGN WITHDRAWAL =================

@app.route("/campaign/<int:campaign_id>/withdraw", methods=["POST"])
def campaign_withdraw(campaign_id):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "CREATOR":
        return "Only creators can withdraw campaign funds.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                u.status,
                u.creator_approval_status,
                cr.creator_id,
                c.campaign_id,
                c.title,
                c.raised_amount,
                c.status AS campaign_status
            FROM users u
            JOIN creators cr
                ON cr.user_id = u.user_id
            JOIN campaigns c
                ON c.creator_id = cr.creator_id
            WHERE u.user_id = %s
              AND c.campaign_id = %s
            FOR UPDATE
        """, (session["user_id"], campaign_id))

        creator_campaign = cursor.fetchone()

        if not creator_campaign:
            return "Campaign not found or you are not the campaign creator.", 404

        if creator_campaign["status"] != "ACTIVE":
            return "Your creator account is not active.", 403

        if creator_campaign["creator_approval_status"] != "APPROVED":
            return "Your creator account is not approved.", 403

        if creator_campaign["campaign_status"] not in ("APPROVED", "ACTIVE", "COMPLETED"):
            return "Funds can only be withdrawn from an approved, active, or completed campaign.", 403

        amount_text = request.form.get("amount", "").strip()

        try:
            amount = Decimal(amount_text)
        except Exception:
            return "Enter a valid withdrawal amount.", 400

        if amount <= 0:
            return "Withdrawal amount must be greater than ₹0.", 400

        cursor.execute("""
            SELECT bank_account_id, status
            FROM creator_bank_accounts
            WHERE creator_id = %s
            LIMIT 1
        """, (creator_campaign["creator_id"],))

        bank_account = cursor.fetchone()

        if not bank_account:
            return "Please register your bank account before requesting a withdrawal.", 400

        if bank_account["status"] != "ACTIVE":
            return "Your registered bank account is not active.", 400

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS reserved_amount
            FROM creator_withdrawals
            WHERE campaign_id = %s
              AND creator_id = %s
              AND status IN ('PENDING', 'APPROVED', 'COMPLETED')
        """, (campaign_id, creator_campaign["creator_id"]))

        reserved_row = cursor.fetchone()
        reserved_amount = Decimal(str(reserved_row["reserved_amount"] or 0))
        raised_amount = Decimal(str(creator_campaign["raised_amount"] or 0))
        available_amount = max(Decimal("0.00"), raised_amount - reserved_amount)

        if amount > available_amount:
            return (
                f"Insufficient available funds for this campaign. "
                f"Available: ₹{available_amount:.2f}"
            ), 400

        cursor.execute("""
            INSERT INTO creator_withdrawals
            (creator_id, campaign_id, bank_account_id, amount, status)
            VALUES (%s, %s, %s, %s, 'PENDING')
        """, (
            creator_campaign["creator_id"],
            campaign_id,
            bank_account["bank_account_id"],
            amount
        ))

        connection.commit()

        return redirect(url_for("campaign_details", campaign_id=campaign_id))

    except Exception as e:
        connection.rollback()
        return f"Withdrawal request failed: {e}", 500

    finally:
        cursor.close()
        connection.close()

# ================= ADMIN - CAMPAIGN WITHDRAWALS =================

@app.route("/admin/withdrawals")
def admin_withdrawals():

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Access denied. Admins only.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                w.withdrawal_id,
                w.amount,
                w.status,
                w.rejection_reason,
                w.requested_at,
                w.reviewed_at,
                c.campaign_id,
                c.title AS campaign_title,
                u.full_name AS creator_name,
                u.email AS creator_email,
                b.account_holder_name,
                b.bank_name,
                b.account_number,
                b.ifsc_code,
                reviewer.full_name AS reviewer_name
            FROM creator_withdrawals w
            JOIN campaigns c
                ON c.campaign_id = w.campaign_id
            JOIN creators cr
                ON cr.creator_id = w.creator_id
            JOIN users u
                ON u.user_id = cr.user_id
            JOIN creator_bank_accounts b
                ON b.bank_account_id = w.bank_account_id
            LEFT JOIN users reviewer
                ON reviewer.user_id = w.reviewed_by
            ORDER BY w.withdrawal_id DESC
        """)

        withdrawals = cursor.fetchall()

        return render_template(
            "admin_withdrawals.html",
            withdrawals=withdrawals
        )

    finally:
        cursor.close()
        connection.close()

@app.route("/admin/withdrawals/<int:withdrawal_id>/review", methods=["POST"])
def review_withdrawal(withdrawal_id):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Access denied. Admins only.", 403

    decision = request.form.get("decision", "").strip().upper()
    rejection_reason = request.form.get("rejection_reason", "").strip()

    if decision not in ("APPROVED", "REJECTED"):
        return "Invalid withdrawal decision.", 400

    if decision == "REJECTED" and not rejection_reason:
        return "Rejection reason is required.", 400

    if len(rejection_reason) > 500:
        return "Rejection reason must be 500 characters or less.", 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                w.withdrawal_id,
                w.creator_id,
                w.campaign_id,
                w.amount,
                w.status,
                w.bank_account_id,
                u.full_name,
                u.email,
                c.title AS campaign_title
            FROM creator_withdrawals w
            JOIN creators cr
                ON cr.creator_id = w.creator_id
            JOIN users u
                ON u.user_id = cr.user_id
            JOIN campaigns c
                ON c.campaign_id = w.campaign_id
            WHERE w.withdrawal_id = %s
            FOR UPDATE
        """, (withdrawal_id,))

        withdrawal = cursor.fetchone()

        if not withdrawal:
            return "Withdrawal request not found.", 404

        if withdrawal["status"] != "PENDING":
            return (
                f"This withdrawal has already been reviewed and is currently "
                f"{withdrawal['status']}."
            ), 409

        cursor.execute("""
            UPDATE creator_withdrawals
            SET
                status = %s,
                rejection_reason = %s,
                reviewed_at = CURRENT_TIMESTAMP,
                reviewed_by = %s
            WHERE withdrawal_id = %s
              AND status = 'PENDING'
        """, (
            decision,
            rejection_reason if decision == "REJECTED" else None,
            session["user_id"],
            withdrawal_id
        ))

        if cursor.rowcount != 1:
            connection.rollback()
            return "The withdrawal could not be reviewed because it was already updated.", 409

        cursor.execute("""
            INSERT INTO admin_logs
            (admin_id, action, description)
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            "CREATOR_WITHDRAWAL_REVIEW",
            f"Admin {session['user_id']} reviewed withdrawal #{withdrawal_id} "
            f"for campaign '{withdrawal['campaign_title']}' and set it to {decision}."
            + (f" Reason: {rejection_reason}" if decision == "REJECTED" else "")
        ))

        connection.commit()

        email_subject = (
            "CrowdCare Campaign Withdrawal Approved"
            if decision == "APPROVED"
            else "CrowdCare Campaign Withdrawal Rejected"
        )

        email_body = f"""Hello {withdrawal['full_name']},

Your withdrawal request for the CrowdCare campaign "{withdrawal['campaign_title']}" has been {decision}.

Amount: ₹{Decimal(str(withdrawal['amount'])):.2f}
"""

        if decision == "REJECTED":
            email_body += f"\nReason: {rejection_reason}\n"

        email_body += "\nRegards,\nCrowdCare Administration\n"

        email_sent = send_creator_email(
            withdrawal["email"],
            withdrawal["full_name"],
            email_subject,
            email_body
        )

        email_connection = get_db_connection()
        email_cursor = email_connection.cursor()

        try:
            email_cursor.execute("""
                INSERT INTO admin_logs
                (admin_id, action, description)
                VALUES (%s, %s, %s)
            """, (
                session["user_id"],
                "CREATOR_EMAIL_SENT" if email_sent else "CREATOR_EMAIL_FAILED",
                f"Withdrawal decision notification for {withdrawal['full_name']} "
                f"({withdrawal['email']}) after {decision} decision."
            ))
            email_connection.commit()
        except Exception:
            email_connection.rollback()
        finally:
            email_cursor.close()
            email_connection.close()

        return redirect(url_for("admin_withdrawals"))

    except Exception as e:
        connection.rollback()
        return f"Withdrawal review failed: {e}", 500

    finally:
        cursor.close()
        connection.close()

# ================= CREATE CAMPAIGN =================

@app.route("/create-campaign", methods=["GET", "POST"])
def create_campaign():

    # User must be logged in
    if "user_id" not in session:
        return redirect("/login")

    # Only CREATOR accounts can create campaigns.
    if session.get("role") != "CREATOR":
        return "Only creators can create campaigns.", 403

    # Creator account must also be approved by an administrator.
    approval_connection = get_db_connection()
    approval_cursor = approval_connection.cursor(dictionary=True)

    try:
        approval_cursor.execute("""
            SELECT status, role, creator_approval_status
            FROM users
            WHERE user_id = %s
        """, (session["user_id"],))

        creator_user = approval_cursor.fetchone()

        if not creator_user:
            session.clear()
            return redirect("/login")

        if creator_user["status"] != "ACTIVE":
            session.clear()
            return "Your account is currently INACTIVE or BLOCKED. Please contact an administrator.", 403

        if creator_user["role"] != "CREATOR":
            session.clear()
            return "Only creators can create campaigns.", 403

        if creator_user["creator_approval_status"] != "APPROVED":
            session.clear()
            return "Your creator account has not been approved by an administrator.", 403

    finally:
        approval_cursor.close()
        approval_connection.close()

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # -----------------------------------------
        # Get categories for the campaign form
        # -----------------------------------------

        cursor.execute("""
            SELECT category_id, category_name
            FROM categories
            ORDER BY category_name
        """)

        categories = cursor.fetchall()

        # -----------------------------------------
        # CREATE CAMPAIGN
        # -----------------------------------------

        if request.method == "POST":

            title = request.form["title"]
            category_id = request.form["category_id"]
            description = request.form["description"]
            target_amount = request.form["target_amount"]
            city = request.form["city"]
            start_date = request.form["start_date"]
            end_date = request.form["end_date"]

            # -----------------------------------------
            # IMPORTANT:
            # Get creator_id from creators table
            # using the logged-in user's user_id
            # -----------------------------------------

            cursor.execute("""
                SELECT creator_id
                FROM creators
                WHERE user_id = %s
            """, (session["user_id"],))

            creator = cursor.fetchone()

            if not creator:

                return "Creator profile not found.", 400

            creator_id = creator["creator_id"]

            # -----------------------------------------
            # Insert campaign
            # -----------------------------------------

            cursor.execute("""
                INSERT INTO campaigns
                (
                    creator_id,
                    category_id,
                    title,
                    description,
                    target_amount,
                    raised_amount,
                    city,
                    start_date,
                    end_date,
                    status
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    0,
                    %s,
                    %s,
                    %s,
                    'PENDING'
                )
            """, (
                creator_id,
                category_id,
                title,
                description,
                target_amount,
                city,
                start_date,
                end_date
            ))

            connection.commit()

            return redirect("/campaigns")

        # -----------------------------------------
        # Show campaign creation form
        # -----------------------------------------

        return render_template(
            "create_campaign.html",
            categories=categories
        )

    except Exception as e:

        connection.rollback()

        return f"Campaign creation failed: {e}"

    finally:

        cursor.close()
        connection.close()

   
    # ================= ADMIN CAMPAIGN MANAGEMENT =================

@app.route("/admin/campaigns")
def admin_campaigns():

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Only admins can access campaign management.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT
                c.campaign_id,
                c.title,
                c.description,
                c.target_amount,
                c.raised_amount,
                c.city,
                c.start_date,
                c.end_date,
                c.status,
                cat.category_name,
                u.full_name AS creator_name,
                (
                    SELECT COUNT(*)
                    FROM donations d
                    WHERE d.campaign_id = c.campaign_id
                ) AS donation_count,
                (
                    SELECT COALESCE(SUM(w.amount), 0)
                    FROM creator_withdrawals w
                    WHERE w.campaign_id = c.campaign_id
                      AND w.status = 'COMPLETED'
                ) AS completed_withdrawal_amount
            FROM campaigns c
            JOIN creators cr
                ON c.creator_id = cr.creator_id
            JOIN users u
                ON cr.user_id = u.user_id
            LEFT JOIN categories cat
                ON c.category_id = cat.category_id
            ORDER BY c.campaign_id DESC
        """)

        campaigns = cursor.fetchall()

        return render_template(
            "admin_campaigns.html",
            campaigns=campaigns
        )

    finally:

        cursor.close()
        connection.close()
# ================= ADMIN - USERS =================

@app.route("/admin/users")
def admin_users():

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Access denied. Admins only.", 403

    selected_role = request.args.get("role", "ALL")

    if selected_role not in ("ALL", "CREATOR", "DONOR", "ADMIN"):
        selected_role = "ALL"

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        base_query = """
            SELECT
                user_id,
                full_name,
                email,
                phone,
                role,
                status,
                creator_approval_status,
                created_at
            FROM users
        """

        if selected_role in ("CREATOR", "DONOR", "ADMIN"):
            cursor.execute(
                base_query + " WHERE role = %s ORDER BY user_id DESC",
                (selected_role,)
            )
        else:
            cursor.execute(
                base_query + " ORDER BY user_id DESC"
            )

        users = cursor.fetchall()

        return render_template(
            "admin_users.html",
            users=users,
            selected_role=selected_role
        )

    finally:
        cursor.close()
        connection.close()


# ================= ADMIN - UPDATE USER STATUS =================

@app.route("/admin/user/<int:user_id>/status", methods=["POST"])
def admin_update_user_status(user_id):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Access denied. Admins only.", 403

    if user_id == session["user_id"]:
        return "You cannot change the status of your own admin account.", 400

    new_status = request.form.get("status")

    if new_status not in ("ACTIVE", "INACTIVE", "BLOCKED"):
        return "Invalid user status.", 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT user_id, full_name, status, role
            FROM users
            WHERE user_id = %s
            FOR UPDATE
        """, (user_id,))

        user = cursor.fetchone()

        if not user:
            return "User not found.", 404

        # Status rules are role-specific:
        # CREATOR -> ACTIVE / INACTIVE / BLOCKED
        # DONOR   -> ACTIVE / INACTIVE only
        # ADMIN   -> ACTIVE / INACTIVE only
        if user["role"] in ("DONOR", "ADMIN") and new_status == "BLOCKED":
            return f"{user['role']} accounts cannot be blocked. Use INACTIVE instead.", 400

        # Never allow the system to remove the last active admin account.
        if user["role"] == "ADMIN" and new_status != "ACTIVE":
            cursor.execute("""
                SELECT COUNT(*) AS active_admins
                FROM users
                WHERE role = 'ADMIN'
                  AND status = 'ACTIVE'
            """)
            active_admins = cursor.fetchone()["active_admins"]

            if active_admins <= 1 and user["status"] == "ACTIVE":
                return "At least one active admin account must remain.", 400

        if user["status"] == new_status:
            return "User already has this status.", 400

        cursor.execute("""
            UPDATE users
            SET status = %s
            WHERE user_id = %s
        """, (new_status, user_id))

        cursor.execute("""
            INSERT INTO admin_logs
            (admin_id, action, description)
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            "UPDATE_USER_STATUS",
            f"Changed user {user['full_name']} (ID: {user_id}) status "
            f"from {user['status']} to {new_status}."
        ))

        connection.commit()

        return redirect("/admin/users")

    except Exception as e:
        connection.rollback()
        return f"User status update failed: {e}", 500

    finally:
        cursor.close()
        connection.close()

# ================= ADMIN - UPDATE USER ROLE =================

@app.route("/admin/user/<int:user_id>/role", methods=["POST"])
def admin_update_user_role(user_id):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Access denied. Admins only.", 403

    if user_id == session["user_id"]:
        return "You cannot change your own admin role.", 400

    new_role = request.form.get("role")

    if new_role not in ("ADMIN", "DONOR", "CREATOR"):
        return "Invalid user role.", 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT user_id, full_name, role, status, creator_approval_status
            FROM users
            WHERE user_id = %s
        """, (user_id,))

        user = cursor.fetchone()

        if not user:
            return "User not found.", 404

        old_role = user["role"]

        if old_role == new_role:
            return "User already has this role.", 400

        # Do not allow the system to end up without an active admin.
        if old_role == "ADMIN" and new_role != "ADMIN" and user.get("status") == "ACTIVE":
            cursor.execute("""
                SELECT COUNT(*) AS active_admins
                FROM users
                WHERE role = 'ADMIN'
                  AND status = 'ACTIVE'
            """)
            active_admins = cursor.fetchone()["active_admins"]

            if active_admins <= 1:
                return "At least one active admin account must remain.", 400

        if new_role == "CREATOR":
            # Becoming a creator always requires explicit admin approval.
            new_approval_status = "PENDING"
        else:
            # Approval status is irrelevant for non-creator roles.
            new_approval_status = user["creator_approval_status"]

        cursor.execute("""
            UPDATE users
            SET role = %s,
                creator_approval_status = %s
            WHERE user_id = %s
        """, (new_role, new_approval_status, user_id))

        if new_role == "DONOR":
            cursor.execute("""
                INSERT IGNORE INTO donors (user_id)
                VALUES (%s)
            """, (user_id,))

        elif new_role == "CREATOR":
            cursor.execute("""
                INSERT IGNORE INTO creators (user_id)
                VALUES (%s)
            """, (user_id,))

        cursor.execute("""
            INSERT INTO admin_logs
            (admin_id, action, description)
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            "UPDATE_USER_ROLE",
            f"Changed user {user['full_name']} (ID: {user_id}) role "
            f"from {old_role} to {new_role}."
        ))

        connection.commit()

        return redirect("/admin/users")

    except Exception as e:
        connection.rollback()
        return f"User role update failed: {e}", 500

    finally:
        cursor.close()
        connection.close()


# ================= ADMIN - CREATOR APPROVAL =================

@app.route("/admin/user/<int:user_id>/creator-approval", methods=["POST"])
def admin_creator_approval(user_id):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Access denied. Admins only.", 403

    approval_status = request.form.get("approval_status")
    documents_viewed = request.form.get("documents_viewed") == "YES"
    review_confirmed = request.form.get("review_confirmed") == "YES"
    rejection_reason = request.form.get("rejection_reason", "").strip()

    if approval_status not in ("APPROVED", "REJECTED"):
        return "Invalid creator approval status.", 400

    # Approval requires an explicit confirmation that the admin reviewed
    # the complete submission and all four documents.
    if approval_status == "APPROVED":
        if not documents_viewed:
            return "Please confirm that you have viewed all submitted documents before approving.", 400

        if not review_confirmed:
            return "Please confirm that the submitted information and documents have been verified before approving.", 400

    # Rejection always requires a meaningful reason.
    if approval_status == "REJECTED":
        if not rejection_reason:
            return "A rejection reason is required.", 400

        if len(rejection_reason) > 500:
            return "Rejection reason cannot exceed 500 characters.", 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.email,
                u.role,
                u.creator_approval_status,

                cv.verification_id,
                cv.status AS verification_status,
                cv.organization_name,
                cv.ngo_registration_number,
                cv.ngo_email,
                cv.location,
                cv.registration_certificate,
                cv.pan_document,
                cv.representative_id_document,
                cv.bank_proof

            FROM users u

            LEFT JOIN creator_verifications cv
                ON cv.user_id = u.user_id

            WHERE u.user_id = %s

            FOR UPDATE
        """, (user_id,))

        user = cursor.fetchone()

        if not user:
            return "User not found.", 404

        if user["role"] != "CREATOR":
            return "Creator approval can only be applied to creator accounts.", 400

        if not user["verification_id"]:
            return "Creator verification has not been submitted.", 400

        # Do not approve or reject an already reviewed submission.
        if user["verification_status"] != "PENDING":
            return (
                f"This verification has already been reviewed "
                f"and is currently {user['verification_status']}."
            ), 400

        required_documents = (
            user["registration_certificate"],
            user["pan_document"],
            user["representative_id_document"],
            user["bank_proof"]
        )

        required_details = (
            user["organization_name"],
            user["ngo_registration_number"],
            user["ngo_email"],
            user["location"]
        )

        if any(not value for value in required_documents + required_details):
            return (
                "Creator verification is incomplete. All required information "
                "and documents must be submitted before a decision."
            ), 400

        old_status = user["creator_approval_status"]

        # Update the account approval status.
        cursor.execute("""
            UPDATE users
            SET creator_approval_status = %s
            WHERE user_id = %s
              AND role = 'CREATOR'
        """, (approval_status, user_id))

        # Store the exact admin who reviewed the submission and the review time.
        cursor.execute("""
            UPDATE creator_verifications
            SET
                status = %s,
                rejection_reason = %s,
                reviewed_at = CURRENT_TIMESTAMP,
                reviewed_by = %s
            WHERE user_id = %s
              AND status = 'PENDING'
        """, (
            approval_status,
            rejection_reason if approval_status == "REJECTED" else None,
            session["user_id"],
            user_id
        ))

        if cursor.rowcount != 1:
            connection.rollback()
            return "The verification could not be updated because it was already reviewed.", 409

        # Keep a permanent audit entry.
        log_description = (
            f"Admin {session['user_id']} reviewed creator "
            f"{user['full_name']} (ID: {user_id}) and changed verification "
            f"from {old_status} to {approval_status}."
        )

        if approval_status == "APPROVED":
            log_description += (
                " Admin confirmed that all submitted information and documents "
                "were reviewed and verified."
            )
        else:
            log_description += f" Reason: {rejection_reason}"

        cursor.execute("""
            INSERT INTO admin_logs
            (admin_id, action, description)
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            "CREATOR_ACCOUNT_APPROVAL",
            log_description
        ))

        connection.commit()

        # ================= CREATOR EMAIL NOTIFICATION =================
        #
        # The database decision is already committed before sending email.
        # Therefore an email/SMTP failure cannot undo the approval/rejection.

        if approval_status == "REJECTED":

            email_subject = "CrowdCare Creator Verification Rejected"

            email_body = f"""Hello {user['full_name']},

Your Creator verification request on CrowdCare has been reviewed by the CrowdCare administration team.

Unfortunately, your request has been REJECTED.

Organization / NGO:
{user['organization_name']}

Reason for rejection:
{rejection_reason}

Please review the reason above, correct the issue, and resubmit your Creator verification documents from CrowdCare.

Your account will remain unable to use Creator features until your verification is approved.

Regards,
CrowdCare Administration
"""

        else:

            email_subject = "CrowdCare Creator Verification Approved"

            email_body = f"""Hello {user['full_name']},

Your Creator verification request on CrowdCare has been reviewed and APPROVED.

Organization / NGO:
{user['organization_name']}

Your Creator account has now been approved by the CrowdCare administration team.

You can log in to CrowdCare and use the Creator features.

Regards,
CrowdCare Administration
"""

        email_sent = send_creator_email(
            user["email"],
            user["full_name"],
            email_subject,
            email_body
        )

        # Record email delivery attempt in the admin log without changing
        # the already completed verification decision.
        email_action = (
            "CREATOR_EMAIL_SENT"
            if email_sent
            else "CREATOR_EMAIL_FAILED"
        )

        email_description = (
            f"Creator decision notification for {user['full_name']} "
            f"({user['email']}) after {approval_status} decision."
        )

        if not email_sent:
            email_description += (
                " Email could not be sent. Check SMTP/mail configuration."
            )

        email_connection = get_db_connection()
        email_cursor = email_connection.cursor()

        try:
            email_cursor.execute("""
                INSERT INTO admin_logs
                (admin_id, action, description)
                VALUES (%s, %s, %s)
            """, (
                session["user_id"],
                email_action,
                email_description
            ))

            email_connection.commit()

        except Exception as email_log_error:
            email_connection.rollback()
            print(
                "[EMAIL LOG] Could not record email notification result: "
                f"{email_log_error}"
            )

        finally:
            email_cursor.close()
            email_connection.close()

        return redirect(url_for("admin_creator_verifications"))

    except Exception as e:
        connection.rollback()
        return f"Creator approval failed: {e}", 500

    finally:
        cursor.close()
        connection.close()


# ================= ADMIN - CREATOR VERIFICATIONS =================

@app.route("/admin/creator-verifications")
def admin_creator_verifications():

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Access denied. Admins only.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                cv.verification_id,
                cv.user_id,
                cv.organization_name,
                cv.ngo_registration_number,
                cv.ngo_email,
                cv.location,
                cv.registration_certificate,
                cv.pan_document,
                cv.representative_id_document,
                cv.bank_proof,
                cv.status AS verification_status,
                cv.rejection_reason,
                cv.submitted_at,
                cv.reviewed_at,
                cv.reviewed_by,
                u.full_name,
                u.email AS account_email,
                u.phone,
                u.creator_approval_status,
                reviewer.full_name AS reviewer_name
            FROM creator_verifications cv
            JOIN users u
                ON cv.user_id = u.user_id
            LEFT JOIN users reviewer
                ON cv.reviewed_by = reviewer.user_id
            WHERE u.role = 'CREATOR'
            ORDER BY
                CASE cv.status
                    WHEN 'PENDING' THEN 1
                    WHEN 'REJECTED' THEN 2
                    WHEN 'APPROVED' THEN 3
                    ELSE 4
                END,
                cv.submitted_at DESC
        """)

        verifications = cursor.fetchall()

        return render_template(
            "admin_creator_verifications.html",
            verifications=verifications
        )

    finally:
        cursor.close()
        connection.close()


@app.route("/admin/creator-verification/<int:verification_id>/document/<string:document_type>")
def admin_creator_verification_document(verification_id, document_type):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Access denied. Admins only.", 403

    allowed_documents = {
        "registration_certificate": "registration_certificate",
        "pan_document": "pan_document",
        "representative_id": "representative_id_document",
        "bank_proof": "bank_proof"
    }

    column = allowed_documents.get(document_type)

    if not column:
        return "Invalid document type.", 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(f"""
            SELECT {column} AS document_path
            FROM creator_verifications
            WHERE verification_id = %s
        """, (verification_id,))

        verification = cursor.fetchone()

        if not verification or not verification["document_path"]:
            return "Document not found.", 404

        document_path = os.path.abspath(verification["document_path"])
        upload_root = os.path.abspath(CREATOR_VERIFICATION_FOLDER)

        if (
            not document_path.startswith(upload_root + os.sep)
            or not os.path.isfile(document_path)
        ):
            return "Document is unavailable.", 404

        return send_file(document_path, as_attachment=False)

    finally:
        cursor.close()
        connection.close()


# ================= ADMIN - DONATIONS =================

@app.route("/admin/donations")
def admin_donations():

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Access denied. Admins only.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                d.donation_id,
                d.amount,
                d.payment_method,
                d.status,
                d.donation_date,
                c.title AS campaign_title,
                u.full_name AS donor_name,
                u.email AS donor_email
            FROM donations d

            JOIN campaigns c
                ON d.campaign_id = c.campaign_id

            JOIN donors dr
                ON d.donor_id = dr.donor_id

            JOIN users u
                ON dr.user_id = u.user_id

            ORDER BY d.donation_date DESC
        """)

        donations = cursor.fetchall()

        return render_template(
            "admin_donations.html",
            donations=donations
        )

    finally:
        cursor.close()
        connection.close()
        # ================= ADMIN - REPORTS =================

@app.route("/admin/reports")
def admin_reports():

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Access denied. Admins only.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # ================= PLATFORM SUMMARY =================

        cursor.execute("""
            SELECT
                COUNT(*) AS total_campaigns,
                COALESCE(SUM(raised_amount), 0) AS total_raised
            FROM campaigns
        """)
        campaign_summary = cursor.fetchone()

        cursor.execute("""
            SELECT
                COUNT(*) AS total_donations,
                COALESCE(SUM(amount), 0) AS total_donated
            FROM donations
            WHERE status = 'COMPLETED'
        """)
        donation_summary = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*) AS total_donors
            FROM donors
        """)
        donor_summary = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*) AS total_creators
            FROM creators
        """)
        creator_summary = cursor.fetchone()

        # ================= CAMPAIGN STATUS =================

        cursor.execute("""
            SELECT
                status,
                COUNT(*) AS count
            FROM campaigns
            GROUP BY status
        """)
        status_rows = cursor.fetchall()

        status_counts = {
            "PENDING": 0,
            "APPROVED": 0,
            "REJECTED": 0
        }

        for row in status_rows:
            if row["status"] in status_counts:
                status_counts[row["status"]] = row["count"]

        # ================= PAYMENT METHODS =================

        cursor.execute("""
            SELECT
                payment_method,
                COUNT(*) AS count,
                COALESCE(SUM(amount), 0) AS total
            FROM donations
            WHERE status = 'COMPLETED'
            GROUP BY payment_method
            ORDER BY total DESC
        """)
        payment_methods = cursor.fetchall()

        # ================= RECENT DONATIONS =================

        cursor.execute("""
            SELECT
                d.donation_id,
                d.amount,
                d.payment_method,
                d.donation_date,
                u.full_name AS donor_name,
                c.title AS campaign_title
            FROM donations d
            JOIN donors dr
                ON d.donor_id = dr.donor_id
            JOIN users u
                ON dr.user_id = u.user_id
            JOIN campaigns c
                ON d.campaign_id = c.campaign_id
            WHERE d.status = 'COMPLETED'
            ORDER BY d.donation_date DESC
            LIMIT 10
        """)
        recent_donations = cursor.fetchall()

        return render_template(
            "admin_reports.html",
            campaign_summary=campaign_summary,
            donation_summary=donation_summary,
            donor_summary=donor_summary,
            creator_summary=creator_summary,
            status_counts=status_counts,
            payment_methods=payment_methods,
            recent_donations=recent_donations
        )

    finally:
        cursor.close()
        connection.close()



# ================= ADMIN CAMPAIGN SAFETY =================

@app.route("/admin/campaign/<int:campaign_id>/delete", methods=["POST"])
def delete_campaign(campaign_id):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Only admins can delete campaigns.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT campaign_id, title, status
            FROM campaigns
            WHERE campaign_id = %s
            FOR UPDATE
        """, (campaign_id,))

        campaign = cursor.fetchone()

        if not campaign:
            return "Campaign not found.", 404

        # NEVER delete a campaign that has donation history.
        cursor.execute("""
            SELECT COUNT(*) AS donation_count
            FROM donations
            WHERE campaign_id = %s
        """, (campaign_id,))

        donation_count = cursor.fetchone()["donation_count"]

        if donation_count > 0:
            connection.rollback()
            return (
                "This campaign cannot be deleted because it has donation records. "
                "Close the campaign instead and use the refund option if required.",
                409
            )

        cursor.execute("""
            DELETE FROM campaigns
            WHERE campaign_id = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM donations
                  WHERE donations.campaign_id = campaigns.campaign_id
              )
        """, (campaign_id,))

        if cursor.rowcount != 1:
            connection.rollback()
            return "Campaign deletion failed.", 409

        cursor.execute("""
            INSERT INTO admin_logs
            (admin_id, action, description)
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            "DELETE_CAMPAIGN",
            f"Deleted campaign: {campaign['title']} "
            f"(ID: {campaign_id}, status: {campaign['status']}). "
            "No donation records existed."
        ))

        connection.commit()
        return redirect("/admin/campaigns")

    except Exception as e:
        connection.rollback()
        return f"Campaign deletion failed: {e}", 500

    finally:
        cursor.close()
        connection.close()


@app.route("/admin/campaign/<int:campaign_id>/close", methods=["POST"])
def close_campaign(campaign_id):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Only admins can close campaigns.", 403

    closure_reason = request.form.get("closure_reason", "").strip()

    if not closure_reason:
        closure_reason = "Campaign closed by CrowdCare administration."

    if len(closure_reason) > 500:
        return "Closure reason cannot exceed 500 characters.", 400

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT campaign_id, title, status
            FROM campaigns
            WHERE campaign_id = %s
            FOR UPDATE
        """, (campaign_id,))

        campaign = cursor.fetchone()

        if not campaign:
            return "Campaign not found.", 404

        if campaign["status"] not in ("APPROVED", "ACTIVE"):
            return (
                f"This campaign cannot be closed because its current status is "
                f"{campaign['status']}.",
                400
            )

        cursor.execute("""
            UPDATE campaigns
            SET
                status = 'CLOSED',
                closure_reason = %s,
                closed_at = CURRENT_TIMESTAMP,
                closed_by = %s
            WHERE campaign_id = %s
              AND status IN ('APPROVED', 'ACTIVE')
        """, (
            closure_reason,
            session["user_id"],
            campaign_id
        ))

        if cursor.rowcount != 1:
            connection.rollback()
            return "Campaign could not be closed because its status changed.", 409

        cursor.execute("""
            INSERT INTO admin_logs
            (admin_id, action, description)
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            "CLOSE_CAMPAIGN",
            f"Closed campaign: {campaign['title']} (ID: {campaign_id}). "
            f"Reason: {closure_reason}"
        ))

        connection.commit()
        return redirect(url_for("campaign_details", campaign_id=campaign_id))

    except Exception as e:
        connection.rollback()
        return f"Campaign closure failed: {e}", 500

    finally:
        cursor.close()
        connection.close()


@app.route("/admin/campaign/<int:campaign_id>/refund-all", methods=["POST"])
def refund_all_donors(campaign_id):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Only admins can process campaign refunds.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Lock the campaign so only one refund operation can run at a time.
        cursor.execute("""
            SELECT campaign_id, title, status, raised_amount
            FROM campaigns
            WHERE campaign_id = %s
            FOR UPDATE
        """, (campaign_id,))

        campaign = cursor.fetchone()

        if not campaign:
            return "Campaign not found.", 404

        if campaign["status"] != "CLOSED":
            return "The campaign must be CLOSED before refunds can be processed.", 400

        # A creator withdrawal means campaign money has already been recorded
        # as paid out. Do not pretend those funds can also be refunded.
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS completed_withdrawal_amount
            FROM creator_withdrawals
            WHERE campaign_id = %s
              AND status = 'COMPLETED'
        """, (campaign_id,))

        completed_withdrawal_amount = Decimal(
            str(cursor.fetchone()["completed_withdrawal_amount"] or 0)
        )

        if completed_withdrawal_amount > 0:
            return (
                "Refund cannot be processed because this campaign already has "
                f"completed creator withdrawals totaling ₹{completed_withdrawal_amount:.2f}. "
                "This must be handled manually.",
                409
            )

        cursor.execute("""
            SELECT
                d.donation_id,
                d.amount,
                u.full_name AS donor_name,
                u.email AS donor_email
            FROM donations d
            JOIN donors dr
                ON d.donor_id = dr.donor_id
            JOIN users u
                ON dr.user_id = u.user_id
            WHERE d.campaign_id = %s
              AND d.status = 'COMPLETED'
            FOR UPDATE
        """, (campaign_id,))

        donations_to_refund = cursor.fetchall()

        if not donations_to_refund:
            return "There are no completed donations to refund.", 400

        total_refund = sum(
            (Decimal(str(row["amount"])) for row in donations_to_refund),
            Decimal("0.00")
        )

        cursor.execute("""
            UPDATE donations
            SET
                status = 'REFUNDED',
                refund_reason = %s,
                refunded_at = CURRENT_TIMESTAMP
            WHERE campaign_id = %s
              AND status = 'COMPLETED'
        """, (
            "Campaign closed by CrowdCare administration.",
            campaign_id
        ))

        # After all completed donations are refunded, the campaign's current
        # raised amount becomes zero. The donation records themselves remain.
        cursor.execute("""
            UPDATE campaigns
            SET raised_amount = GREATEST(0, raised_amount - %s)
            WHERE campaign_id = %s
        """, (total_refund, campaign_id))

        cursor.execute("""
            INSERT INTO admin_logs
            (admin_id, action, description)
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            "REFUND_ALL_CAMPAIGN_DONATIONS",
            f"Refunded {len(donations_to_refund)} donation(s) for closed campaign "
            f"'{campaign['title']}' (ID: {campaign_id}), total ₹{total_refund:.2f}."
        ))

        connection.commit()

        # Send donor notifications AFTER the database transaction is committed.
        # Email failure does not undo the refund status change.
        for donation in donations_to_refund:
            email_subject = "CrowdCare Donation Refund Processed"
            email_body = f"""Hello {donation['donor_name']},

Your donation to the CrowdCare campaign "{campaign['title']}" has been marked as REFUNDED.

Donation amount: ₹{Decimal(str(donation['amount'])):.2f}

The campaign was closed by the CrowdCare administration team due to the following reason:
{campaign.get('closure_reason') or 'Campaign closed by CrowdCare administration.'}

CrowdCare has recorded this refund against your donation.

Regards,
CrowdCare Administration
"""

            send_creator_email(
                donation["donor_email"],
                donation["donor_name"],
                email_subject,
                email_body
            )

        return redirect(url_for("campaign_details", campaign_id=campaign_id))

    except Exception as e:
        connection.rollback()
        return f"Campaign refund failed: {e}", 500

    finally:
        cursor.close()
        connection.close()


# ================= ADMIN APPROVE CAMPAIGN =================

@app.route("/admin/campaign/<int:campaign_id>/approve", methods=["POST"])
def approve_campaign(campaign_id):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Only admins can approve campaigns.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Check campaign and lock it during the status decision.
        cursor.execute("""
            SELECT campaign_id, title, status
            FROM campaigns
            WHERE campaign_id = %s
            FOR UPDATE
        """, (campaign_id,))

        campaign = cursor.fetchone()

        if not campaign:
            return "Campaign not found.", 404

        if campaign["status"] != "PENDING":
            return (
                f"Campaign cannot be approved because its current status is "
                f"{campaign['status']}. Only PENDING campaigns can be approved.",
                400
            )

        cursor.execute("""
            UPDATE campaigns
            SET status = 'APPROVED',
                rejection_reason = NULL
            WHERE campaign_id = %s
              AND status = 'PENDING'
        """, (campaign_id,))

        if cursor.rowcount != 1:
            connection.rollback()
            return "Campaign approval failed because its status changed.", 409

        # Add admin log
        cursor.execute("""
            INSERT INTO admin_logs
            (admin_id, action, description)
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            "APPROVE_CAMPAIGN",
            f"Approved campaign: {campaign['title']} (ID: {campaign_id})"
        ))

        connection.commit()

        return redirect("/admin/campaigns")

    except Exception as e:
        connection.rollback()
        return f"Campaign approval failed: {e}", 500

    finally:
        cursor.close()
        connection.close()
        # ================= ADMIN REJECT CAMPAIGN =================

@app.route("/admin/campaign/<int:campaign_id>/reject", methods=["POST"])
def reject_campaign(campaign_id):

    if "user_id" not in session:
        return redirect("/login")

    if session.get("role") != "ADMIN":
        return "Only admins can reject campaigns.", 403

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT campaign_id, title, status
            FROM campaigns
            WHERE campaign_id = %s
            FOR UPDATE
        """, (campaign_id,))

        campaign = cursor.fetchone()

        if not campaign:
            return "Campaign not found.", 404

        if campaign["status"] != "PENDING":
            return (
                f"Campaign cannot be rejected because its current status is "
                f"{campaign['status']}. Only PENDING campaigns can be rejected.",
                400
            )

        rejection_reason = request.form.get(
            "rejection_reason",
            "Campaign rejected by administrator."
        ).strip()

        if not rejection_reason:
            rejection_reason = "Campaign rejected by administrator."

        if len(rejection_reason) > 500:
            return "Rejection reason cannot exceed 500 characters.", 400

        cursor.execute("""
            UPDATE campaigns
            SET status = 'REJECTED',
                rejection_reason = %s
            WHERE campaign_id = %s
              AND status = 'PENDING'
        """, (
            rejection_reason,
            campaign_id
        ))

        if cursor.rowcount != 1:
            connection.rollback()
            return "Campaign rejection failed because its status changed.", 409

        cursor.execute("""
            INSERT INTO admin_logs
            (admin_id, action, description)
            VALUES (%s, %s, %s)
        """, (
            session["user_id"],
            "REJECT_CAMPAIGN",
            f"Rejected campaign: {campaign['title']} (ID: {campaign_id}). Reason: {rejection_reason}"
        ))

        connection.commit()

        return redirect("/admin/campaigns")

    except Exception as e:
        connection.rollback()
        return f"Campaign rejection failed: {e}", 500

    finally:
        cursor.close()
        connection.close()
# ================= LOGOUT =================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")

# ================= RUN APPLICATION =================

if __name__ == "__main__":

    app.run(host="127.0.0.1", port=5000, debug=True)