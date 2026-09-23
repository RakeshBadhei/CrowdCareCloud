-- CrowdCare Creator Verification
-- Run this once in the crowdcare database.

CREATE TABLE IF NOT EXISTS creator_verifications (
    verification_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,

    organization_name VARCHAR(200) NOT NULL,
    ngo_registration_number VARCHAR(100) NOT NULL,
    ngo_email VARCHAR(150) NOT NULL,
    location VARCHAR(255) NOT NULL,

    registration_certificate VARCHAR(500) NOT NULL,
    pan_document VARCHAR(500) NOT NULL,
    representative_id_document VARCHAR(500) NOT NULL,
    bank_proof VARCHAR(500) NOT NULL,

    status ENUM('PENDING', 'APPROVED', 'REJECTED') NOT NULL DEFAULT 'PENDING',
    rejection_reason VARCHAR(500) NULL,

    submitted_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP NULL DEFAULT NULL,
    reviewed_by INT NULL,

    CONSTRAINT fk_creator_verification_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_creator_verification_reviewer
        FOREIGN KEY (reviewed_by) REFERENCES users(user_id)
        ON DELETE SET NULL
);
