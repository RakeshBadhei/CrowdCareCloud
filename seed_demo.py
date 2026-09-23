from decimal import Decimal
from werkzeug.security import generate_password_hash
from db import get_db_connection

DEMO_USERS = [
    ("Demo Admin", "admin@crowdcare.demo", "Admin@123", "ADMIN", "9000000001", "APPROVED"),
    ("Demo Donor", "donor@crowdcare.demo", "Donor@123", "DONOR", "9000000002", "APPROVED"),
    ("Demo Donor Two", "donor2@crowdcare.demo", "Donor@123", "DONOR", "9000000003", "APPROVED"),
    ("Aarav Foundation", "creator@crowdcare.demo", "Creator@123", "CREATOR", "9000000004", "APPROVED"),
    ("HopeBridge Collective", "creator2@crowdcare.demo", "Creator@123", "CREATOR", "9000000005", "APPROVED"),
    ("GreenSteps India", "creator3@crowdcare.demo", "Creator@123", "CREATOR", "9000000006", "APPROVED"),
]

CAMPAIGNS = [
    ("Medical", "Help a Child Receive Urgent Treatment", "Support urgent treatment and medicines for a child whose family is struggling to meet hospital costs.", 50000, 12000, "Bhubaneswar"),
    ("Education", "Higher Education Scholarship for Rural Girls", "Help ambitious students from rural communities cover tuition, learning materials and essential study support.", 200000, 45002, "Angul"),
    ("Animal Welfare", "Safe Shelter for Rescued Street Animals", "Create temporary shelter, food and veterinary support for rescued street animals.", 80000, 28400, "Cuttack"),
    ("Environment", "Restore a Community Green Space", "Bring a neglected community space back to life with native trees, clean-up drives and local volunteers.", 75000, 31900, "Bhubaneswar"),
    ("Community", "Meals for Families in Need", "Provide essential food kits and cooked meals to families facing a difficult month.", 60000, 37200, "Talcher"),
    ("Disaster Relief", "Emergency Supplies After the Floods", "Help affected families access food, hygiene supplies and essential household items.", 150000, 68200, "Balasore"),
    ("Medical", "Dialysis Support for a Working Family", "Help cover recurring treatment expenses while a family works through a difficult medical period.", 125000, 54100, "Cuttack"),
    ("Education", "Laptops for Community Learners", "Put reliable learning devices in the hands of students who currently study without access to a computer.", 100000, 47600, "Jatni"),
]

def find_user(cur, email):
    cur.execute("SELECT user_id, role FROM users WHERE email=%s", (email,))
    return cur.fetchone()

def get_or_create_category(cur, name):
    cur.execute("SELECT category_id FROM categories WHERE category_name=%s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO categories(category_name, description) VALUES(%s,%s)",
                (name, f"{name} fundraising campaigns"))
    return cur.lastrowid

def main():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        user_ids = {}
        for full_name, email, password, role, phone, approval in DEMO_USERS:
            row = find_user(cur, email)
            if row:
                user_ids[email] = row[0]
                cur.execute("""
                    UPDATE users
                    SET status='ACTIVE',
                        role=%s,
                        creator_approval_status=%s,
                        email_verified=1
                    WHERE user_id=%s
                """, (role, approval, row[0]))
            else:
                cur.execute("""
                    INSERT INTO users
                    (full_name,email,password,role,phone,status,creator_approval_status,email_verified)
                    VALUES(%s,%s,%s,%s,%s,'ACTIVE',%s,1)
                """, (full_name, email, generate_password_hash(password), role, phone, approval))
                user_ids[email] = cur.lastrowid

        creators = [
            ("creator@crowdcare.demo", "Aarav Foundation", "Bhubaneswar"),
            ("creator2@crowdcare.demo", "HopeBridge Collective", "Cuttack"),
            ("creator3@crowdcare.demo", "GreenSteps India", "Angul"),
        ]
        creator_ids = []
        for email, org, city in creators:
            uid = user_ids[email]
            cur.execute("SELECT creator_id FROM creators WHERE user_id=%s", (uid,))
            row = cur.fetchone()
            if row:
                cid = row[0]
            else:
                cur.execute("INSERT INTO creators(user_id,organization_name,city,address) VALUES(%s,%s,%s,%s)",
                            (uid, org, city, city + ", Odisha"))
                cid = cur.lastrowid
            creator_ids.append(cid)

        donor_ids = []
        for email in ["donor@crowdcare.demo","donor2@crowdcare.demo"]:
            uid = user_ids[email]
            cur.execute("SELECT donor_id FROM donors WHERE user_id=%s", (uid,))
            row = cur.fetchone()
            if row:
                did = row[0]
            else:
                cur.execute("INSERT INTO donors(user_id,city) VALUES(%s,%s)", (uid, "Odisha"))
                did = cur.lastrowid
            donor_ids.append(did)

        campaign_ids = []
        for i, (cat_name,title,desc,target,raised,city) in enumerate(CAMPAIGNS):
            creator_id = creator_ids[i % len(creator_ids)]
            cat_id = get_or_create_category(cur, cat_name)
            cur.execute("SELECT campaign_id FROM campaigns WHERE title=%s", (title,))
            row = cur.fetchone()
            if row:
                cid = row[0]
                cur.execute("""
                    UPDATE campaigns SET status='ACTIVE', target_amount=%s,
                    raised_amount=%s, city=%s, category_id=%s, creator_id=%s
                    WHERE campaign_id=%s
                """, (target, raised, city, cat_id, creator_id, cid))
            else:
                cur.execute("""
                    INSERT INTO campaigns
                    (creator_id,category_id,title,description,target_amount,raised_amount,city,start_date,end_date,status)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,CURDATE(),DATE_ADD(CURDATE(),INTERVAL 45 DAY),'ACTIVE')
                """, (creator_id, cat_id, title, desc, target, raised, city))
                cid = cur.lastrowid
            campaign_ids.append(cid)

        # Seed one completed donation per demo campaign so the displayed
        # raised totals and donation history remain internally consistent.
        payment_methods = ["UPI", "CARD", "NET_BANKING", "WALLET"]
        for i, (cid, campaign) in enumerate(zip(campaign_ids, CAMPAIGNS)):
            cur.execute("SELECT COUNT(*) FROM donations WHERE campaign_id=%s", (cid,))
            if cur.fetchone()[0] == 0:
                donor_id = donor_ids[i % len(donor_ids)]
                amount = Decimal(str(campaign[4]))
                cur.execute("""
                    INSERT INTO donations(campaign_id,donor_id,amount,payment_method,status)
                    VALUES(%s,%s,%s,%s,'COMPLETED')
                """, (cid, donor_id, amount, payment_methods[i % len(payment_methods)]))

        conn.commit()
        print("CrowdCare demo data is ready.")
        print("OTP for every login: 6969")
        for row in DEMO_USERS:
            print(f"{row[3]:7}  {row[1]:30}  {row[2]}")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
