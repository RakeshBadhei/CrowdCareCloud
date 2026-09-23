-- =========================================================
-- CrowdCare Database
-- Cloud-Based Fundraising & Donation Platform
-- =========================================================

CREATE DATABASE IF NOT EXISTS crowdcare;

USE crowdcare;


-- =========================================================
-- 1. USERS
-- =========================================================

CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,

    full_name VARCHAR(100) NOT NULL,

    email VARCHAR(100) NOT NULL UNIQUE,

    password VARCHAR(255) NOT NULL,

    role ENUM('ADMIN', 'DONOR', 'CREATOR') NOT NULL,

    phone VARCHAR(15),

    status ENUM('ACTIVE', 'INACTIVE', 'BLOCKED')
        NOT NULL DEFAULT 'ACTIVE',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 2. CREATORS
-- =========================================================

CREATE TABLE creators (
    creator_id INT AUTO_INCREMENT PRIMARY KEY,

    user_id INT NOT NULL UNIQUE,

    organization_name VARCHAR(150),

    address VARCHAR(255),

    city VARCHAR(100),

    profile_image VARCHAR(255),

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);


-- =========================================================
-- 3. DONORS
-- =========================================================

CREATE TABLE donors (
    donor_id INT AUTO_INCREMENT PRIMARY KEY,

    user_id INT NOT NULL UNIQUE,

    address VARCHAR(255),

    city VARCHAR(100),

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);


-- =========================================================
-- 4. CATEGORIES
-- =========================================================

CREATE TABLE categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,

    category_name VARCHAR(100) NOT NULL UNIQUE,

    description VARCHAR(255),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- 5. CAMPAIGNS
-- =========================================================

CREATE TABLE campaigns (
    campaign_id INT AUTO_INCREMENT PRIMARY KEY,

    creator_id INT NOT NULL,

    category_id INT NOT NULL,

    title VARCHAR(200) NOT NULL,

    description TEXT NOT NULL,

    target_amount DECIMAL(12,2) NOT NULL,

    raised_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00,

    cover_image VARCHAR(255),

    city VARCHAR(100),

    start_date DATE NOT NULL,

    end_date DATE NOT NULL,

    status ENUM(
        'PENDING',
        'ACTIVE',
        'REJECTED',
        'COMPLETED',
        'CLOSED'
    ) NOT NULL DEFAULT 'PENDING',

    rejection_reason VARCHAR(500),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (creator_id)
        REFERENCES creators(creator_id)
        ON DELETE CASCADE,

    FOREIGN KEY (category_id)
        REFERENCES categories(category_id)
        ON DELETE RESTRICT
);


-- =========================================================
-- 6. DONATIONS
-- =========================================================

CREATE TABLE donations (
    donation_id INT AUTO_INCREMENT PRIMARY KEY,

    campaign_id INT NOT NULL,

    donor_id INT NOT NULL,

    amount DECIMAL(12,2) NOT NULL,

    payment_method ENUM(
        'UPI',
        'CARD',
        'NET_BANKING',
        'WALLET'
    ) NOT NULL,

    status ENUM(
        'COMPLETED',
        'FAILED',
        'REFUNDED'
    ) NOT NULL DEFAULT 'COMPLETED',

    donation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (campaign_id)
        REFERENCES campaigns(campaign_id)
        ON DELETE CASCADE,

    FOREIGN KEY (donor_id)
        REFERENCES donors(donor_id)
        ON DELETE CASCADE
);


-- =========================================================
-- 7. CAMPAIGN UPDATES
-- =========================================================

CREATE TABLE campaign_updates (
    update_id INT AUTO_INCREMENT PRIMARY KEY,

    campaign_id INT NOT NULL,

    title VARCHAR(200) NOT NULL,

    description TEXT NOT NULL,

    image VARCHAR(255),

    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (campaign_id)
        REFERENCES campaigns(campaign_id)
        ON DELETE CASCADE
);


-- =========================================================
-- 8. NOTIFICATIONS
-- =========================================================

CREATE TABLE notifications (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,

    user_id INT NOT NULL,

    message VARCHAR(500) NOT NULL,

    status ENUM('READ', 'UNREAD')
        NOT NULL DEFAULT 'UNREAD',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);


-- =========================================================
-- 9. ADMIN LOGS
-- =========================================================

CREATE TABLE admin_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,

    admin_id INT NOT NULL,

    action VARCHAR(100) NOT NULL,

    description VARCHAR(500),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (admin_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);


-- =========================================================
-- 10. CONTACT MESSAGES
-- =========================================================

CREATE TABLE contact_messages (
    message_id INT AUTO_INCREMENT PRIMARY KEY,

    name VARCHAR(100) NOT NULL,

    email VARCHAR(100) NOT NULL,

    subject VARCHAR(200),

    message TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- DEFAULT CATEGORIES
-- =========================================================

INSERT INTO categories
    (category_name, description)
VALUES
    ('Medical', 'Medical treatment and healthcare fundraising'),

    ('Education', 'Education fees, scholarships and learning support'),

    ('Animal Welfare', 'Animal rescue, treatment and welfare'),

    ('Disaster Relief', 'Support for people affected by disasters'),

    ('Environment', 'Environmental and conservation causes'),

    ('Community', 'Community development and social causes');


-- =========================================================
-- VERIFY TABLES
-- =========================================================

SHOW TABLES;