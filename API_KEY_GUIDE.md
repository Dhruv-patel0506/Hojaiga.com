# HOJAIGA API KEY GUIDE - FREE VS PAID SERVICES

**Date:** October 2, 2026  
**Purpose:** Guide for finding API keys and understanding free vs paid services

---

## Overview

This guide explains how to get API keys for various services, which ones are free, and how to implement a system where:
- **You (admin)** can use free APIs to keep Hojaiga free
- **Other users** can provide their own API keys (free or paid) for better performance
- **Cost responsibility** is on the user who provides the API key

---

## Service Comparison: Free vs Paid

| Service | Free Tier | Paid Tier | Key Required | Notes |
|---------|-----------|-----------|---------------|-------|
| **Gmail API** | ✅ FREE (Quota) | ✅ Paid (Enterprise) | ✅ Yes | 100-500 requests/day free |
| **Slack API** | ✅ FREE (Limited) | ✅ Paid (Pro+) | ✅ Yes | Rate limits on free tier |
| **Discord API** | ✅ FREE (Generous) | ❌ No paid tier | ✅ Yes | 50 requests/second free |
| **WhatsApp Business API** | ❌ PAID | ✅ Paid | ✅ Yes | Requires business account |
| **GitHub API** | ✅ FREE (5000/hr) | ✅ Paid (Enterprise) | ✅ Yes | Very generous free tier |
| **Google Sheets API** | ✅ FREE (Quota) | ✅ Paid (Workspace) | ✅ Yes | Part of Google API |
| **Notion API** | ✅ FREE (Limited) | ✅ Paid (Plus) | ✅ Yes | Integration rate limits |
| **Trello API** | ✅ FREE (250 requests/day) | ✅ Paid (Business) | ✅ Yes | Basic tier is free |
| **Jira API** | ✅ FREE (Cloud) | ✅ Paid (Data Center) | ✅ Yes | Free for cloud users |
| **Telegram API** | ✅ FREE (Generous) | ❌ No paid tier | ✅ Yes | Bot API is free |
| **OpenAI (GPT)** | ✅ FREE (Credits) | ✅ Paid (API) | ✅ Yes | $5 free credits, then paid |

---

## FREE API Services (Recommended for Free Hojaiga)

### 1. Discord API ✅ FREE
**Cost:** Completely free  
**Rate Limit:** 50 requests/second  
**Best For:** Discord bots, message sending, channel management

**How to Get API Key:**
1. Go to https://discord.com/developers/applications
2. Click "New Application"
3. Fill in app details (name, description)
4. Go to "Bot" section
5. Click "Add Bot"
6. Click "Reset Token" to get your bot token
7. Enable bot permissions:
   - Send Messages
   - Read Messages
   - Read Message History
   - Connect
   - Join Servers
8. Copy your **Bot Token** (starts with `MTA...` or similar)
9. Also copy your **Application ID** (snowflake number)

**Key Format:** `MTA...` (Bot Token)  
**Documentation:** https://discord.com/developers/docs/intro

---

### 2. Telegram API ✅ FREE
**Cost:** Completely free  
**Rate Limit:** Very generous  
**Best For:** Telegram bots, message sending, file sharing

**How to Get API Key:**
1. Open Telegram and search for @BotFather
2. Send `/newbot` command
3. Follow instructions to name your bot
4. You'll receive an API token (starts with `bot_token:`)
5. Copy the token (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

**Key Format:** `123456789:ABC...`  
**Documentation:** https://core.telegram.org/bots/api

---

### 3. GitHub API ✅ FREE (Generous)
**Cost:** 5000 requests/hour free  
**Rate Limit:** Very generous  
**Best For:** Repository management, issues, pull requests

**How to Get API Key:**
1. Go to https://github.com/settings/tokens
2. Click "Generate new token" (classic or fine-grained)
3. For classic token:
   - Select scopes (repo, user, etc.)
   - Click "Generate token"
4. Copy the token (starts with `ghp_` or `github_pat_`)
5. For fine-grained token:
   - Select "Generate new token (fine-grained)"
   - Name your token
   - Select repositories and permissions
   - Click "Generate token"

**Key Format:** `ghp_...` or `github_pat_...`  
**Documentation:** https://docs.github.com/en/rest

---

### 4. Trello API ✅ FREE (Basic)
**Cost:** 250 requests/day free  
**Rate Limit:** Limited but usable  
**Best For:** Board management, card operations

**How to Get API Key:**
1. Go to https://trello.com/app-key
2. You'll see two keys:
   - **Key** (for API requests)
   - **Token** (for OAuth/authorized requests)
3. Copy both keys

**Key Format:** Random alphanumeric string  
**Documentation:** https://developer.atlassian.com/cloud/trello/rest

---

## PAID API Services (Users Can Provide Their Own Keys)

### 1. Gmail API ⚠️ QUOTA LIMITED
**Free Tier:** 100-500 requests/day  
**Paid Tier:** $0.05 per 1000 requests (Gmail API)  
**Best For:** Email automation, Gmail integration

**How to Get API Key:**
1. Go to https://console.cloud.google.com/
2. Create a new project or select existing
3. Go to "APIs & Services" → "Library"
4. Search for "Gmail API" and enable it
5. Go to "APIs & Services" → "Credentials"
6. Click "Create Credentials" → "OAuth client ID"
7. Configure OAuth consent screen:
   - Application type: Desktop app
   - App name: Hojaiga
   - User support email: your email
8. Download the `credentials.json` file
9. For testing, you can use the Gmail API with OAuth

**Key Format:** OAuth credentials (JSON file)  
**Documentation:** https://developers.google.com/gmail/api

**Free Tier Limitation:** Only 100-500 requests/day for testing  
**Recommendation:** Users should provide their own Gmail API for production use

---

### 2. WhatsApp Business API ❌ PAID
**Cost:** ~$0.005 per message  
**Best For:** WhatsApp automation, message sending

**How to Get API Key:**
1. You need a Meta Business Account
2. Go to https://developers.facebook.com/apps
3. Create a new app
4. Add "WhatsApp" product
5. Get your WhatsApp Business API credentials
6. Requires verification of business

**Key Format:** Access token  
**Documentation:** https://developers.facebook.com/docs/whatsapp

**Recommendation:** NOT recommended for free Hojaiga (paid service)

---

### 3. Notion API ⚠️ RATE LIMITED
**Free Tier:** Limited integration rate  
**Paid Tier:** $8/month (Plus plan)  
**Best For:** Notion pages, databases

**How to Get API Key:**
1. Go to https://www.notion.so/my-integrations
2. Click "Develop your own integrations"
3. Create a new integration
4. Copy the "Internal Integration Token"

**Key Format:** `secret_...`  
**Documentation:** https://developers.notion.com

**Free Tier Limitation:** Rate limits on API calls  
**Recommendation:** Free tier usable for light automation

---

### 4. Google Sheets API ⚠️ QUOTA LIMITED
**Free Tier:** Part of Google API quota  
**Paid Tier:** Google Workspace  
**Best For:** Spreadsheet automation

**How to Get API Key:**
1. Go to https://console.cloud.google.com/
2. Create a new project
3. Enable "Google Sheets API"
4. Create OAuth credentials
5. Download `credentials.json`

**Key Format:** OAuth credentials (JSON file)  
**Documentation:** https://developers.google.com/sheets/api

**Free Tier Limitation:** Daily quota limits  
**Recommendation:** Usable for free tier with reasonable usage

---

## Implementation: User-Provided API Keys

### System Design

**Principle:** You (admin) use free APIs. Users can provide their own API keys (free or paid) for better performance or additional features.

**Architecture:**
```
Hojaiga System
├── Default API Keys (Free APIs - You Provide)
│   ├── Discord API Key (Free)
│   ├── Telegram API Key (Free)
│   ├── GitHub API Key (Free)
│   └── Trello API Key (Free)
│
└── User API Keys (Optional - User Provides)
    ├── Gmail API Credentials (User's own)
    ├── Notion API Token (User's own)
    ├── OpenAI API Key (User's own)
    └── Custom API Keys (User's own)
```

### Configuration File Structure

Create `config/api_keys.json`:
```json
{
  "default_keys": {
    "discord": {
      "bot_token": "YOUR_DISCORD_BOT_TOKEN",
      "application_id": "YOUR_DISCORD_APP_ID"
    },
    "telegram": {
      "bot_token": "YOUR_TELEGRAM_BOT_TOKEN"
    },
    "github": {
      "access_token": "YOUR_GITHUB_TOKEN"
    },
    "trello": {
      "key": "YOUR_TRELLO_KEY",
      "token": "YOUR_TRELLO_TOKEN"
    }
  },
  "user_keys": {
    "gmail": {
      "enabled": false,
      "credentials_path": null,
      "provided_by": null
    },
    "notion": {
      "enabled": false,
      "api_key": null,
      "provided_by": null
    },
    "openai": {
      "enabled": false,
      "api_key": null,
      "provided_by": null
    }
  }
}
```

### API Key Manager Implementation

Create `core_organs/api_key_manager.py`:
```python
"""
API Key Manager for Hojaiga

Manages default API keys (free) and user-provided API keys (free or paid).
Cost responsibility is on the key provider.
"""

import json
import os
from typing import Optional, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger("hojaiga.api_key_manager")


class APIKeyManager:
    """Manages API keys for various services."""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = r"D:\new_automation\config\api_keys.json"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load API key configuration."""
        if not self.config_path.exists():
            self.config_path.parent.mkdir(exist_ok=True)
            default_config = {
                "default_keys": {},
                "user_keys": {}
            }
            with open(self.config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            return default_config
        
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def _save_config(self):
        """Save API key configuration."""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def get_key(self, service: str, use_user_key: bool = False) -> Optional[str]:
        """
        Get API key for a service.
        
        Args:
            service: Service name (discord, telegram, github, etc.)
            use_user_key: Whether to use user-provided key (if available)
        
        Returns:
            API key or None
        """
        # Try user key first if requested
        if use_user_key and service in self.config.get("user_keys", {}):
            user_key_config = self.config["user_keys"][service]
            if user_key_config.get("enabled", False):
                key = user_key_config.get("api_key") or user_key_config.get("bot_token") or user_key_config.get("access_token")
                if key:
                    logger.info(f"[APIKeyManager] Using user-provided key for {service}")
                    return key
        
        # Fall back to default key
        if service in self.config.get("default_keys", {}):
            key = self.config["default_keys"][service]
            logger.info(f"[APIKeyManager] Using default key for {service}")
            return key
        
        logger.warning(f"[APIKeyManager] No key found for {service}")
        return None
    
    def set_user_key(self, service: str, key: str, provided_by: str = "user"):
        """
        Set a user-provided API key.
        
        Args:
            service: Service name
            key: API key
            provided_by: Who provided the key (user identifier)
        """
        if "user_keys" not in self.config:
            self.config["user_keys"] = {}
        
        self.config["user_keys"][service] = {
            "enabled": True,
            "api_key": key,
            "provided_by": provided_by,
            "added_at": None  # Could add timestamp
        }
        
        self._save_config()
        logger.info(f"[APIKeyManager] User key set for {service} by {provided_by}")
    
    def remove_user_key(self, service: str):
        """Remove a user-provided API key."""
        if "user_keys" in self.config and service in self.config["user_keys"]:
            del self.config["user_keys"][service]
            self._save_config()
            logger.info(f"[APIKeyManager] User key removed for {service}")
    
    def get_key_info(self, service: str) -> Dict[str, Any]:
        """Get information about API key for a service."""
        info = {
            "service": service,
            "has_default_key": service in self.config.get("default_keys", {}),
            "has_user_key": service in self.config.get("user_keys", {}),
            "user_key_enabled": False
        }
        
        if info["has_user_key"]:
            info["user_key_enabled"] = self.config["user_keys"][service].get("enabled", False)
            info["provided_by"] = self.config["user_keys"][service].get("provided_by", "unknown")
        
        return info
```

---

## Step-by-Step Guide: Getting Free API Keys

### Discord API (FREE) - RECOMMENDED
1. Go to https://discord.com/developers/applications
2. Click "New Application"
3. Name: "Hojaiga Bot"
4. Go to "Bot" → "Add Bot"
5. Click "Reset Token" → Copy token
6. Enable permissions: Send Messages, Read Messages, Connect
7. Copy token and Application ID

### Telegram API (FREE) - RECOMMENDED
1. Open Telegram → Search @BotFather
2. Send `/newbot`
3. Name your bot: "HojaigaBot"
4. Copy the API token you receive

### GitHub API (FREE) - RECOMMENDED
1. Go to https://github.com/settings/tokens
2. Click "Generate new token" (classic)
3. Select scopes: repo, user
4. Click "Generate token"
5. Copy the token

### Trello API (FREE) - RECOMMENDED
1. Go to https://trello.com/app-key
2. Copy the Key and Token shown

---

## Step-by-Step Guide: Paid APIs (User-Provided)

### Gmail API (QUOTA LIMITED)
1. Go to https://console.cloud.google.com/
2. Create project → Enable Gmail API
3. Create OAuth credentials
4. Download `credentials.json`
5. User can provide this file to Hojaiga

### Notion API (RATE LIMITED)
1. Go to https://www.notion.so/my-integrations
2. Click "Develop your own integrations"
3. Create integration → Copy token

### OpenAI API (PAID)
1. Go to https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Copy the API key

---

## Best Practices for API Key Management

### 1. Security
- ✅ Never commit API keys to Git
- ✅ Use environment variables for sensitive keys
- ✅ Store keys in a separate config file (not in code)
- ✅ Add `config/` to `.gitignore`

### 2. User Experience
- ✅ Clearly label which APIs are free vs paid
- ✅ Show user when they're using their own key
- ✅ Warn user about potential costs
- ✅ Allow user to remove their keys at any time

### 3. Transparency
- ✅ Document rate limits for each API
- ✅ Show usage statistics to user
- ✅ Alert user when approaching limits
- ✅ Provide alternative options when limits reached

---

## Cost Summary

### Your Cost (Admin, Building Free Hojaiga)
- **Discord API:** FREE
- **Telegram API:** FREE
- **GitHub API:** FREE
- **Trello API:** FREE
- **Total:** $0/month

### User Cost (If They Provide Keys)
- **Discord API:** FREE (even with their key)
- **Telegram API:** FREE (even with their key)
- **GitHub API:** FREE (even with their key)
- **Trello API:** FREE (even with their key)
- **Gmail API:** FREE (up to quota) or PAID (if they exceed quota)
- **Notion API:** FREE (limited) or PAID ($8/month for Plus)
- **OpenAI API:** PAID (usage-based, $0.002/1K tokens)

---

## Recommendation

### For Free Hojaiga (Your Build)
Use these FREE APIs:
1. ✅ **Discord API** - Completely free
2. ✅ **Telegram API** - Completely free
3. ✅ **GitHub API** - Very generous free tier
4. ✅ **Trello API** - 250 requests/day free

### For Users Who Want More
Allow users to provide their own keys for:
1. ⚠️ **Gmail API** - If they need high-volume email automation
2. ⚠️ **Notion API** - If they need higher rate limits
3. ⚠️ **OpenAI API** - If they want AI-powered features

**Important:** Make it clear that cost responsibility is on the user when they provide their own key.

---

## Next Steps

1. **Get your free API keys** following the guides above
2. **Create the config file** structure
3. **Implement the API Key Manager** in Hojaiga
4. **Add UI for users to provide their own keys**
5. **Add cost warnings** when users enable paid services
6. **Document which services are free vs paid**

---

**Status:** ✅ GUIDE COMPLETE  
**Recommendation:** Use FREE APIs for your build, allow users to provide their own keys for additional features
