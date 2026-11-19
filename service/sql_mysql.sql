-- Même modèle que stockage.py, pour MySQL 8 (projet Symfony).
-- La requête d'agrégation de stockage.py fonctionne telle quelle sur MySQL
-- (remplacer les paramètres nommés par ceux de Doctrine DBAL).
CREATE TABLE commande (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    boutique_id    INT NOT NULL,
    telephone      VARCHAR(20)  NOT NULL,
    telephone_hash CHAR(64)     NOT NULL,
    libelle        VARCHAR(255) NULL,
    montant        DECIMAL(10,3) NULL,
    statut         ENUM('PENDING','DELIVERED','REFUSED','NOT_COLLECTED') NOT NULL,
    date_commande  DATE NOT NULL,
    empreinte      CHAR(64) NOT NULL UNIQUE,
    lot_id         VARCHAR(32) NULL,
    INDEX idx_commande_tel (telephone_hash, statut, date_commande)
) ENGINE=InnoDB;

CREATE TABLE signalement (
    id             BIGINT AUTO_INCREMENT PRIMARY KEY,
    boutique_id    INT NULL,
    telephone_hash CHAR(64) NOT NULL,
    motif          VARCHAR(255) NULL,
    statut         ENUM('EN_ATTENTE','CONFIRME','REJETE') NOT NULL DEFAULT 'EN_ATTENTE',
    INDEX idx_signalement_tel (telephone_hash, statut)
) ENGINE=InnoDB;
