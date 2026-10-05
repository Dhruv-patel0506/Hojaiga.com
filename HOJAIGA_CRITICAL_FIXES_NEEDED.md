# HOJAIGA CRITICAL FIXES NEEDED

**Date:** October 2, 2026  
**Status:** Identified Issues from Real Task Execution

---

## Issues Identified

### 1. Gmail Recognition Issue ❌
**Problem:** When user says "open gmail", system tries to launch "mail" (Windows Mail) instead of recognizing "gmail" as a web service that should use Chrome with session cookies.

**Current Behavior:**
```
[LAUNCH] VerbAliasEngine resolved 'mail' -> 'mail'
[SCAN] 'mail' not open, auto-launching before scan
```

**Expected Behavior:**
- Recognize "gmail" as a web service
- Launch Chrome with Gmail URL
- Use session cookies for login if available
- If not logged in, let user login and store session cookies

**Fix Applied:** ✅
- Added "gmail" and related keywords to VerbAliasEngine to map to "google chrome"
- Keywords: gmail, gmail account, open gmail, gmail web, check gmail, gmail inbox, gmail spam, delete gmail, remove spam, gmail emails, webmail, web mail, mail.google.com, google mail

---

### 2. Brain Compilation Not Creating Agent Structure ❌
**Problem:** Brain (Organ 36) compiles tasks but does not create proper checkpoints and agent hierarchy for:
- Permanent agents
- Sub-substance agents
- Temporary agents

**Current Behavior:**
```
[ORGAN_36] Compiled task into 2 verified dynamic sequential steps (success=True)
```

**Expected Behavior:**
- Create checkpoints for each phase
- Determine agent types (permanent/sub-substance/temporary)
- Generate proper agent spawn instructions
- Include agent tier information

**Fix Needed:** ⏳
- Update Organ 36 to emit agent hierarchy information
- Add checkpoint generation
- Include agent type classification
- Generate sub-substance/temporary agent spawn instructions

---

### 3. App Aliasing Not Working ❌
**Problem:** VerbAliasEngine is not properly mapping task verbs to apps in all cases.

**Current Behavior:**
- Some mappings work (notepad, chrome)
- Gmail mapping was missing
- Function aliasing may not be working

**Fix Applied:** ✅
- Added Gmail to VerbAliasEngine
- Need to verify function aliasing is working

---

### 4. Session Cookie Management ❌
**Problem:** System doesn't properly handle session cookies for web services like Gmail.

**Expected Behavior:**
- Store session cookies after first login
- Reuse session cookies for subsequent visits
- Let user login if cookies expired

**Fix Needed:** ⏳
- Implement session cookie storage
- Add cookie management to CDP runtime
- Implement cookie validation and refresh

---

## Priority Fixes

### High Priority (Critical for Real Tasks)
1. ✅ Gmail recognition - FIXED
2. ⏳ Brain compilation agent structure - NEEDS FIX
3. ⏳ Session cookie management - NEEDS FIX

### Medium Priority
4. ⏳ Function aliasing verification
5. ⏳ App aliasing improvements

---

## Next Steps

1. Fix Brain Compilation (Organ 36)
   - Add agent type classification
   - Generate checkpoints
   - Create agent spawn instructions

2. Implement Session Cookie Management
   - Add cookie storage to CDP runtime
   - Implement cookie validation
   - Add login detection

3. Test Real Gmail Task
   - Launch Chrome with Gmail
   - Handle login if needed
   - Store session cookies
   - Perform spam deletion

---

**Status:** Partially Fixed (1/4 issues resolved)
