-- ============================================
-- HOJAIGA UI Knowledge Schema
-- Optimized for rapid-fire popup tracking
-- ============================================

-- Ensure the database exists
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'hojaiga_knowledge')
BEGIN
    CREATE DATABASE hojaiga_knowledge;
END
GO

USE hojaiga_knowledge;
GO

-- ============================================
-- ui_scanned: Core popup/control tracking
-- ============================================
IF OBJECT_ID('ui_scanned', 'U') IS NOT NULL DROP TABLE ui_scanned;
CREATE TABLE ui_scanned (
    id INT IDENTITY(1,1) PRIMARY KEY,
    app_id NVARCHAR(255) NOT NULL,
    version NVARCHAR(50) NOT NULL,
    sig NVARCHAR(64) NOT NULL,              -- MD5 signature of control
    layout_hash VARCHAR(64) DEFAULT '',      -- MD5 of UI layout matrix
    window_title NVARCHAR(255) DEFAULT '',   -- OS Window Header Name
    target_x INT DEFAULT 0,                 -- Click X-coordinate
    target_y INT DEFAULT 0,                 -- Click Y-coordinate
    resolution_action NVARCHAR(100) DEFAULT '', -- Action label
    parent_path NVARCHAR(MAX) DEFAULT '',    -- UI trace path
    info NVARCHAR(MAX),                     -- JSON metadata
    last_scanned FLOAT DEFAULT 0,           -- Unix timestamp
    captured_at DATETIME DEFAULT GETDATE()
);

-- Optimization Index: Fast lookups by app+version+sig
CREATE NONCLUSTERED INDEX IX_ui_scanned_lookup 
ON ui_scanned (app_id, version, sig);

-- Optimization Index: Fast popup history checks
CREATE NONCLUSTERED INDEX IX_ui_scanned_popup 
ON ui_scanned (window_title, layout_hash);
GO

-- ============================================
-- ui_knowledge: Layout tree snapshots
-- ============================================
IF OBJECT_ID('ui_knowledge', 'U') IS NOT NULL DROP TABLE ui_knowledge;
CREATE TABLE ui_knowledge (
    id INT IDENTITY(1,1) PRIMARY KEY,
    app_id NVARCHAR(255) NOT NULL,
    version NVARCHAR(50) NOT NULL,
    page_key NVARCHAR(255) NOT NULL,
    tree_hash NVARCHAR(64) NOT NULL,
    ui_tree NVARCHAR(MAX),
    interactive_elements NVARCHAR(MAX),
    last_scanned DATETIME DEFAULT GETDATE()
);

CREATE NONCLUSTERED INDEX IX_ui_knowledge_lookup 
ON ui_knowledge (app_id, version, page_key);
GO

-- ============================================
-- popup_history: Cached popup resolutions
-- ============================================
IF OBJECT_ID('popup_history', 'U') IS NOT NULL DROP TABLE popup_history;
CREATE TABLE popup_history (
    id INT IDENTITY(1,1) PRIMARY KEY,
    popup_title NVARCHAR(500) NOT NULL,
    layout_hash VARCHAR(64) DEFAULT '',
    popup_type NVARCHAR(100) DEFAULT '',
    target_x INT DEFAULT 0,
    target_y INT DEFAULT 0,
    resolution_action NVARCHAR(MAX),
    parent_path NVARCHAR(1000) DEFAULT '',
    occurrences INT DEFAULT 1,
    last_seen DATETIME DEFAULT GETDATE(),
    created_at DATETIME DEFAULT GETDATE()
);

CREATE NONCLUSTERED INDEX IX_popup_history_lookup 
ON popup_history (popup_title, layout_hash);
GO

-- ============================================
-- code_fixes: Aider fix tracking
-- ============================================
IF OBJECT_ID('code_fixes', 'U') IS NOT NULL DROP TABLE code_fixes;
CREATE TABLE code_fixes (
    id INT IDENTITY(1,1) PRIMARY KEY,
    app_id NVARCHAR(255),
    version NVARCHAR(50),
    popup_title NVARCHAR(500),
    eye_analysis NVARCHAR(MAX),
    fix_instruction NVARCHAR(MAX),
    success BIT DEFAULT 0,
    created_at DATETIME DEFAULT GETDATE()
);
GO

PRINT 'Schema created successfully.';
GO
