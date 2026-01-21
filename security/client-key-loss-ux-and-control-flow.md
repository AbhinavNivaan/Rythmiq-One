# Client-Side Key Loss: UX Handling & Irreversible Failure Control Flow

**Version:** 1.0  
**Date:** 2 January 2026  
**Classification:** Blue Team - Client-Side Security & UX  
**Status:** Enforced Implementation Standard

---

## Executive Summary

This document specifies client-side handling and UX for **irreversible key loss scenarios**. Key loss is permanent by design. There is no recovery, no server-side help, no silent re-keying, and no soft fallback paths. This standard ensures:

1. **Explicit user warning** at every decision point
2. **No implicit data access** after key loss  
3. **No silent re-keying** or key regeneration
4. **No server intervention** language (system cannot help)
5. **Irreversible failure is unavoidable** (users cannot ignore or dismiss warnings)

---

## Design Philosophy

**Core Principle:** Key loss must be treated as a **permanent, irreversible business event** that the user cannot undo through the system. The UI enforces this reality by:

- Forcing explicit acknowledgment of permanent data loss (no dismissible warnings)
- Blocking access to encrypted data after key loss (no "try again" options)
- Providing offline recovery options only (recovery codes, printed backups)
- Removing any suggestion that the server can help

**User Responsibility:** Once a key is lost, the user's recourse is entirely offline:
- If they have recovery codes, they can restore their master key
- If they don't, the data is permanently inaccessible

---

## Key Loss Scenario 1: UMK Loss (Master Key Deleted/Unavailable)

### Detection Trigger

UMK loss is detected when:
- Client attempts to decrypt a wrapped DEK
- Local UMK storage (Keychain, DPAPI, IndexedDB, etc.) returns `UNAVAILABLE` or `NOT_FOUND`
- Multiple decryption attempts fail due to missing key material

### UX Flow: UMK Loss Detected

```
[User opens app or attempts to decrypt document]
                ↓
[Client checks: Is UMK present in local secure storage?]
                ↓
[UMK NOT FOUND]
                ↓
[Display BLOCKING full-screen alert (cannot dismiss)]
```

### Full-Screen Warning Dialog (Blocking)

**Title:** `Your Master Key Is Lost - Permanent Data Loss`

**Message:**
```
⚠️  WARNING: PERMANENT DATA LOSS

Your User Master Key (UMK) is no longer available on this device.
This key was the only way to access your encrypted documents.

PERMANENT CONSEQUENCES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• All encrypted documents are now permanently inaccessible
• No recovery is possible without your recovery codes
• Rythmiq One servers cannot help recover this key
• Your data cannot be recovered through any online process

YOUR ONLY OPTIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. If you have recovery codes (printed or written down):
   • Use them to restore your master key to THIS device
   • You will be prompted to enter recovery codes below

2. If you do NOT have recovery codes:
   • Your data is permanently unrecoverable
   • You cannot access documents from this device
   • You can create a new master key for future documents

RECOVERY CODE ENTRY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Text input: "Enter recovery code (8 characters)"]
[Button: "Restore Master Key with Recovery Code"]
[Button: "I Don't Have Recovery Codes" (secondary)]
```

**Behavior:**
- Dialog is **BLOCKING** (cannot close, cannot access app)
- Cannot proceed without choosing an action
- Recovery code input remains visible until user resolves

### Control Flow: UMK Loss Decision Tree

```
User sees UMK Loss warning
        ↓
┌─────────────────────────────────────────┐
│ Does user have recovery codes?          │
└─────────────────────────────────────────┘
        ↙                               ↘
     YES                                NO
      ↓                                  ↓
 [User enters                    [Display: No Recovery
  recovery code]                  Code Path]
      ↓                                  ↓
 [Code validated                 [Show: Documents Lost
  offline on client]              Permanently]
      ↓                                  ↓
 [UMK restored to                [Button: "Create New
  local storage]                  Master Key for
      ↓                            Future Documents"]
 [Unlock documents]                      ↓
      ↓                         [User creates new UMK
 [Prompt to regenerate           (new documents only)]
  new recovery codes]                    ↓
      ↓                         [Documents from OLD
 [User writes down               UMK remain inaccessible]
  codes (CRITICAL)]                      ↓
      ↓                         [User can upload
 [Resume normal                  NEW documents with
  operation]                     new UMK]
```

### Message: No Recovery Codes Available

**Title:** `Your Documents Are Permanently Lost`

**Message:**
```
⚠️  IRREVERSIBLE DATA LOSS

Because you do not have recovery codes and your master key is lost,
ALL documents you encrypted with the lost master key are now
PERMANENTLY AND IRREVOCABLY INACCESSIBLE.

NO RECOVERY IS POSSIBLE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Rythmiq One servers do not have your master key
• No administrator can help recover the key
• No backup or recovery service can restore the data
• Data encrypted with a lost key cannot be recovered through any means

THIS DEVICE REMAINS FUNCTIONAL:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You can create a new master key now and use it for future documents.
All NEW documents will be encrypted with the new key and be accessible.
Old documents will remain inaccessible forever.

NEXT STEPS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Button: "Create New Master Key"]
   └─→ Generate new UMK
   └─→ Show recovery codes immediately
   └─→ FORCE user to write down or print codes
   └─→ Cannot proceed without acknowledgment

[Button: "Exit (You will not be able to access any encrypted documents)"]
   └─→ Close app
   └─→ App remains in locked state until new UMK created
```

### Recovery Code Restoration Flow

**Title:** `Enter Your Recovery Code`

**Message:**
```
To restore your master key using a recovery code:

1. Locate your recovery codes (printed, written, or stored offline)
2. Enter the code exactly as shown (case-sensitive, no spaces)
3. Your master key will be restored to this device only
4. You will immediately regain access to your documents

RECOVERY CODE (8 characters):
[Input field with validation]

[Button: "Restore Master Key"]
[Button: "Back to Options"]
```

**Validation:**
- Code must be exactly 8 characters
- Code is case-sensitive
- Code is validated offline (no server call)
- Invalid code: Display "Invalid recovery code. Check spelling and try again."
- Valid code: Restore UMK to local storage immediately

**After Successful Recovery:**

```
[Dialog: "Master Key Restored Successfully"]

Message:
"Your master key has been restored to this device.

Your encrypted documents are now accessible again.

IMPORTANT: Generate new recovery codes now to prevent
data loss in the future.

[Button: "Generate New Recovery Codes"]
   └─→ Force user to write down codes
   └─→ Proceed only after acknowledgment
"
```

---

## Key Loss Scenario 2: App Reinstall (UMK Not Transferred to New Installation)

### Detection Trigger

App reinstall results in UMK loss when:
- User uninstalls and reinstalls the application
- UMK was stored in app-private encrypted storage (not in OS Keychain/DPAPI)
- New installation has no access to previous app-private storage
- User did not export or back up the UMK

### UX Flow: Post-Reinstall Key Loss Detection

```
[User reinstalls app]
        ↓
[App first launch: Check for existing UMK]
        ↓
[UMK NOT FOUND in local storage]
        ↓
[Check: Are there encrypted documents in cloud storage?]
        ↓
[YES: Documents exist but cannot be decrypted]
        ↓
[Display reinstall warning BEFORE app setup]
```

### Pre-Setup Warning (Before Account Login)

**Title:** `Cannot Access Previous Documents - Master Key Lost`

**Message:**
```
⚠️  INSTALLATION CHANGE DETECTED

You reinstalled Rythmiq One, and your master key was not transferred
to the new installation.

YOUR ENCRYPTED DOCUMENTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Your account has [X] encrypted documents from before the reinstall.
Because your master key is not on this device, you cannot access
any of those documents.

CAN YOUR DOCUMENTS BE RECOVERED?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YES - ONLY if you have recovery codes from your previous installation.
NO - If you don't have recovery codes, all old documents are lost forever.

WHAT ARE YOUR OPTIONS?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Option 1: You have recovery codes
   • Click: "Restore Master Key with Recovery Code"
   • Enter your recovery code to regain access to old documents
   • Your documents will be accessible again on this device

Option 2: You don't have recovery codes
   • Old documents are PERMANENTLY INACCESSIBLE
   • Click: "Continue Without Recovery" to set up a new master key
   • New documents will be encrypted with the new key
   • Old documents will remain inaccessible forever

[Button: "I Have Recovery Codes - Restore Now"]
[Button: "I Don't Have Recovery Codes - Set Up New Master Key"]
```

**Behavior:**
- User MUST choose an action to proceed
- Cannot skip or dismiss this warning
- If choosing "I Have Recovery Codes", jump to recovery code entry (see Section 1)
- If choosing "I Don't Have Recovery Codes", proceed to new UMK setup

### New Master Key Setup (After Reinstall Without Recovery)

**Title:** `Create New Master Key`

**Message:**
```
Since you don't have recovery codes, you will create a new master key
for this installation.

⚠️  WARNING: Your old encrypted documents will remain inaccessible.
They cannot be recovered, and Rythmiq One cannot help.

NEW MASTER KEY SETUP:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1: Enter your password (will be used to derive the master key)
[Password input field]
[Show strength indicator]

Step 2: Confirm password
[Password confirmation field]

Step 3: YOU MUST GENERATE AND STORE RECOVERY CODES
When you click "Create Master Key", you will be forced to:
   • Generate recovery codes
   • Write them down or print them
   • Confirm you have written them down safely

You CANNOT proceed without saving recovery codes.

[Button: "Create Master Key (Next: Generate Recovery Codes)"]
```

**After Master Key Creation:**

```
[BLOCKING: Show generated recovery codes]

[Message: "RECOVERY CODES GENERATED"]

Your recovery codes are your ONLY backup. Keep them safe.

CODES (keep these private and secure):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CODE 1: [8 characters]
CODE 2: [8 characters]
CODE 3: [8 characters]
CODE 4: [8 characters]
CODE 5: [8 characters]

WHAT TO DO NOW:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
☐ Print this page and store in a secure location
☐ Write codes on paper by hand and store offline
☐ Store in a password manager (encrypted)
☐ Store in a hardware security device

DO NOT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✗ Do not take a screenshot (screenshot may be cloud-synced)
✗ Do not email the codes to yourself
✗ Do not store in cloud storage (Dropbox, Google Drive, etc.)
✗ Do not share with anyone
✗ Do not lose them (you have no other backup)

[Checkbox: "I have securely stored my recovery codes"]
[Button: "Continue to App" (disabled until checkbox is checked)]
```

**Control Flow:**

```
User reinstalls → App detects missing UMK
        ↓
[Blocking warning: Cannot access old documents]
        ↓
┌─────────────────────────────────┐
│ User chooses:                   │
├─────────────────────────────────┤
│ 1. Restore with recovery codes  │
│    (goes to recovery flow)      │
│                                 │
│ 2. Create new master key        │
│    (goes to new key setup)      │
└─────────────────────────────────┘
        ↓
[New master key generated]
        ↓
[BLOCKING: Show recovery codes]
        ↓
[Force user to acknowledge codes stored]
        ↓
[Proceed to app setup]
        ↓
[Can only create NEW documents]
```

---

## Key Loss Scenario 3: Browser Refresh / Session Loss (In-Memory Key Cleared)

### Detection Trigger

Session key loss occurs when:
- User refreshes the browser (F5, Cmd+R)
- Browser tab is closed and reopened
- User navigates away and back to the site
- Browser clears session storage (browser settings, privacy mode)
- User's authentication session expires

### UX Flow: Session Key Loss Detection

```
[User refreshes browser or reopens tab]
        ↓
[Client checks: Is UMK in session memory?]
        ↓
[UMK NOT IN MEMORY]
        ↓
[Check: Is UMK in secure storage (IndexedDB)?]
        ↓
[Multiple outcomes]
```

### Case 3a: UMK Still in Secure Storage (Recovery Possible)

**Scenario:** Browser was refreshed, but UMK is still in IndexedDB

```
[Page reloads]
        ↓
[Client retrieves UMK from IndexedDB]
        ↓
[Display: "Please re-enter your password to unlock your documents"]
        ↓
[Block document access until password is re-entered]
```

**Dialog:**

**Title:** `Session Expired - Re-authenticate to Continue`

**Message:**
```
Your session has expired due to:
• Browser refresh
• Page reload
• Navigation away and back

YOUR DOCUMENTS ARE SAFE: Your master key is still stored securely
on this device.

TO CONTINUE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Enter your password to re-derive your master key and continue.

[Password input: "Enter password"]
[Button: "Unlock"]

[Button: "Forget Master Key (Log Out)"]
   └─→ Clears session
   └─→ Forces re-authentication on next session
```

**After Password Entry:**

```
[Client re-derives UMK from password]
        ↓
[Validate: Does re-derived UMK match stored UMK?]
        ↓
[YES: Proceed to document access]
[NO: Display "Incorrect password" and retry]
```

### Case 3b: UMK Missing from Secure Storage (Unrecoverable)

**Scenario:** Browser cache cleared or IndexedDB lost (privacy mode, etc.)

```
[User reopens browser/tab]
        ↓
[Client checks: Is UMK in IndexedDB?]
        ↓
[UMK NOT FOUND]
        ↓
[Check: Can we recover it (recovery codes)?]
        ↓
[Display recovery option or permanent loss message]
```

**Dialog:**

**Title:** `Your Master Key Was Lost During Browser Operation`

**Message:**
```
⚠️  SESSION KEY LOSS DETECTED

When you closed or refreshed your browser, your master key was
cleared from memory. The system cannot find it in local storage.

This may have happened because:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• You were using private browsing mode (storage is temporary)
• Your browser cleared IndexedDB automatically
• Your device storage was full
• A browser update cleared site data
• You manually cleared site data

CAN YOUR DOCUMENTS BE RECOVERED?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YES - If you have recovery codes from a previous login

NO - If you don't have recovery codes, all documents encrypted with
that key are permanently inaccessible.

YOUR OPTIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Option 1: Use recovery codes to restore the master key
   [Button: "I Have Recovery Codes - Restore Now"]
   └─→ Enter recovery code
   └─→ Master key restored to IndexedDB
   └─→ Documents become accessible again

Option 2: You don't have recovery codes
   [Button: "I Don't Have Recovery Codes"]
   └─→ Documents are permanently inaccessible
   └─→ Can create new master key for future documents

PREVENT THIS IN THE FUTURE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Use regular (non-private) browsing mode
✓ Don't clear browser site data
✓ Keep recovery codes written down offline
✓ Log out explicitly instead of just closing the tab
```

**Recovery Code Restoration (Web):**

```
[User enters recovery code]
        ↓
[Client validates code offline]
        ↓
[Code matches stored recovery code hash]
        ↓
[Client restores UMK to IndexedDB]
        ↓
[Display success: "Master Key Restored - Documents Accessible"]
        ↓
[User can access documents again]
```

### Case 3c: Private Browsing Mode (Persistent Loss Risk)

**Title:** `Warning: Private Browsing Mode Detected`

**Message:**
```
⚠️  PRIVATE BROWSING MODE DETECTED

You are using private browsing mode. In private mode:

STORAGE IS TEMPORARY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Your master key is stored in memory ONLY (not saved to disk)
• When you close the tab or browser, the key is PERMANENTLY DELETED
• If you refresh the page, the key is lost
• Private mode storage is not persistent

RISKS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Accidental refresh → Master key lost
• Browser crash → Master key lost
• Tab close → Master key lost
• Computer sleep → Master key lost

RECOMMENDATIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Exit private browsing mode and use regular mode
   (This allows secure storage to disk)
2. OR have your recovery codes ready
   (Recovery codes can restore the key after accidental loss)

DO YOU WANT TO CONTINUE IN PRIVATE MODE?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Button: "I Understand - Continue in Private Mode"]
   └─→ Proceed with in-memory storage only
   └─→ Show warning again at next login

[Button: "Exit Private Mode and Reload"]
   └─→ Close private session
   └─→ Instruct user to reopen in normal mode
```

---

## Key Loss Scenario 4: Secure Storage Failure (Device Storage Corrupted/Inaccessible)

### Detection Trigger

Secure storage failure occurs when:
- **macOS Keychain:** Keychain service crashes or becomes inaccessible
- **iOS Secure Enclave:** Device is in recovery mode or Secure Enclave fails
- **Windows DPAPI:** User password changes, DPAPI state becomes inaccessible
- **Linux libsecret:** Service not available or corrupted state
- **Web IndexedDB:** Quota exceeded, corrupted database, permission denied

### UX Flow: Secure Storage Failure Detection

```
[Client attempts to retrieve UMK from secure storage]
        ↓
[Secure storage returns ERROR]
        ↓
[Errors could be:]
        ├─ UNAVAILABLE (service not running)
        ├─ CORRUPTED (data unreadable)
        ├─ PERMISSION_DENIED (access restricted)
        ├─ QUOTA_EXCEEDED (no space)
        └─ ENCRYPTED_WITH_OLD_KEY (device password changed)
        ↓
[Display error-specific recovery dialog]
```

### Dialog: Secure Storage Failure (Generic)

**Title:** `Master Key Storage Failure - Cannot Access Secure Storage`

**Message:**
```
⚠️  SECURE STORAGE FAILURE

Rythmiq One cannot access your master key because the system's
secure storage is not available.

THIS CAN HAPPEN DUE TO:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Device storage is corrupted
• Operating system service is temporarily unavailable
• Your device password was recently changed (on Windows)
• Device is in an unusual state (recovery mode, startup)
• Browser storage quota exceeded (web only)
• Your user account permissions changed

YOUR DOCUMENTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Your encrypted documents are safe on Rythmiq One servers.
Your master key is stored securely, but currently inaccessible
due to the storage error above.

RECOVERY OPTIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Option 1: Try recovery with recovery codes
   [Button: "Use Recovery Code to Restore"]
   └─→ Recovery codes can restore the key without storage
   └─→ Codes are derived from the key, not stored
   └─→ No device storage required

Option 2: Attempt to fix the storage issue
   [Button: "Troubleshoot Storage" (platform-specific)]
   └─→ macOS: Check Keychain status
   └─→ Windows: Reset DPAPI state
   └─→ Linux: Restart secret service
   └─→ Web: Clear browser cache and retry

Option 3: Manual key recovery (Advanced)
   [Button: "Advanced Recovery Options"]
   └─→ Show manual recovery procedures
   └─→ Requires technical knowledge

[Button: "Exit (Cannot access documents until storage is fixed)"]
```

### Platform-Specific Recovery: Keychain (macOS/iOS)

**Title:** `Keychain Inaccessible - Recovery Steps`

**Message:**
```
⚠️  KEYCHAIN STORAGE ERROR

Your master key is stored in the system Keychain, but Rythmiq One
cannot access it.

POSSIBLE CAUSES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Keychain service crashed or is not running
• Keychain database is corrupted
• Your system clock is out of sync
• System needs to be restarted
• Keychain was reset or restored from backup

QUICK FIXES (Try these first):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Restart your device
   └─→ Close Rythmiq One completely
   └─→ Restart your Mac or iOS device
   └─→ Open Rythmiq One again
   └─→ This fixes most temporary Keychain issues

2. Check system time
   └─→ System Preferences → Date & Time
   └─→ Ensure time is correct
   └─→ Keychain requires accurate system time

3. Unlock Keychain
   └─→ Open Keychain Access (Applications → Utilities)
   └─→ Right-click Keychain → Lock All
   └─→ Right-click Keychain → Unlock
   └─→ Enter your system password

RECOVERY WITH CODES (No Keychain Needed):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If the above steps don't work, use your recovery codes:

[Button: "Use Recovery Code Instead"]
└─→ Recovery codes can restore your key without Keychain
└─→ Does NOT require Keychain to be working
└─→ Works even if Keychain is permanently corrupted

IF KEYCHAIN IS PERMANENTLY LOST:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If you don't have recovery codes and Keychain cannot be recovered:
• Your data is permanently inaccessible
• Apple may be able to restore Keychain from a backup
• Contact Apple Support for Keychain recovery
• Rythmiq One cannot help recover the master key itself

[Button: "Restart and Try Again"]
[Button: "Use Recovery Code"]
[Button: "Exit"]
```

### Platform-Specific Recovery: DPAPI (Windows)

**Title:** `DPAPI Storage Inaccessible - Password Change Detected`

**Message:**
```
⚠️  WINDOWS ENCRYPTION FAILURE

Your master key is encrypted with Windows DPAPI, which became
inaccessible because:

LIKELY CAUSE: Your Windows password was changed
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When you change your Windows password, DPAPI-encrypted data can
become inaccessible until you log in with the new password.

OTHER CAUSES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• User profile was reset or restored from backup
• Device was restored from system image with old encryption
• User account permissions changed
• Windows system was restored to an earlier point

RECOVERY OPTIONS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Option 1: Use recovery codes (Recommended)
   [Button: "Use Recovery Code"]
   └─→ Recovery codes do NOT depend on DPAPI
   └─→ Can restore your key immediately
   └─→ Fastest solution

Option 2: Log out and log back in
   [Button: "Log Out and Retry"]
   └─→ Log out of your Rythmiq One account
   └─→ Log in again with your Windows user account
   └─→ DPAPI will be re-initialized
   └─→ Your key may become accessible

Option 3: Reset DPAPI (Advanced)
   [Button: "Advanced: Reset DPAPI"]
   └─→ This clears stored encryption keys
   └─→ May render key permanently inaccessible
   └─→ Use recovery codes afterward

[Button: "Use Recovery Code" (RECOMMENDED)]
[Button: "Log Out and Retry"]
[Button: "Exit"]
```

### Platform-Specific Recovery: IndexedDB (Web)

**Title:** `Browser Storage Failure - Quota or Corruption`

**Message:**
```
⚠️  BROWSER STORAGE ERROR

Your master key is stored in browser IndexedDB, but storage is
not accessible.

POSSIBLE CAUSES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Browser storage quota is full
• IndexedDB database is corrupted
• Browser auto-cleanup deleted site data
• Your browser privacy settings are too restrictive
• Browser cache was cleared

QUICK FIXES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Free up browser storage space
   ├─ Close other tabs and clear caches
   ├─ Browser Settings → Privacy → Clear browsing data
   │  (only clear cache, NOT site data)
   └─ Reload this page

2. Check browser privacy settings
   ├─ Settings → Privacy and security
   ├─ Ensure IndexedDB is not blocked for this site
   ├─ Reload this page

3. Try a different browser
   └─ Copy your recovery codes to the new browser
   └─ Open Rythmiq One in the new browser
   └─ Use recovery codes to restore your key

RECOVERY WITH CODES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You can use your recovery codes to restore your key:

[Button: "Use Recovery Code"]
└─→ Recovery codes do NOT depend on browser storage
└─→ Can restore your key to any browser or device
└─→ Recommended solution

[Button: "Clear Cache and Retry"]
[Button: "Use Recovery Code" (RECOMMENDED)]
[Button: "Exit"]
```

---

## Recovery Code Entry & Validation

### Universal Recovery Code Flow

Regardless of which scenario triggered key loss, recovery code entry follows this pattern:

```
[User clicks "Use Recovery Code"]
        ↓
[Display recovery code input dialog]
        ↓
[User enters code]
        ↓
[Client validates code offline]
        ↓
[Code matches stored hash]
        ↓
[Client re-derives UMK from code]
        ↓
[UMK restored to secure storage]
        ↓
[Documents become accessible again]
        ↓
[Prompt to generate NEW recovery codes]
```

### Recovery Code Entry Dialog

**Title:** `Enter Your Recovery Code`

**Message:**
```
Enter one of your recovery codes to restore your master key.

Recovery codes are 8-character codes you received when you set up
your account or generated new codes after a previous restore.

ENTER RECOVERY CODE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Input field (auto-uppercase)]

[Button: "Restore Master Key"]
[Button: "Back" / "I Don't Have a Code"]

WHAT IF YOU LOST YOUR CODES?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If you don't have your recovery codes:
• Your data is permanently inaccessible
• You cannot recover your master key
• You can only create a new key for future documents
[Button: "I Don't Have Recovery Codes - Data is Lost"]
```

### Recovery Code Validation Logic (Client-Side)

```
User enters recovery code string
        ↓
[Client normalizes: trim, uppercase, remove spaces]
        ↓
[Client checks: Is code exactly 8 characters?]
        ├─ NO → Display "Code must be 8 characters"
        └─ YES ↓
[Client retrieves stored code_hash from secure storage]
        ↓
[Client derives: test_hash = hash(entered_code)]
        ↓
[Client compares: test_hash == code_hash?]
        ├─ NO → Display "Invalid recovery code. Try again."
        │        (Count invalid attempts; lock after 10)
        └─ YES ↓
[Client re-derives: UMK = kdf(recovery_code, entropy)]
        ↓
[Client validates: Does re-derived UMK match stored hash?]
        ├─ NO → Display "Code is valid but UMK validation failed"
        │        "This should not happen. Contact support."
        └─ YES ↓
[Client stores UMK in secure storage]
        ↓
[Display: "Master Key Restored Successfully"]
```

**Invalid Code Handling:**

```
User enters wrong code
        ↓
[System displays: "Invalid code. Try again."]
        ↓
[Count: Invalid attempts += 1]
        ↓
[After 3 invalid attempts]
        ↓
[Display warning: "You have entered an invalid code 3 times."]
        ↓
[After 10 invalid attempts]
        ↓
[Lock recovery code entry for 1 hour]
        ↓
[Display: "Too many attempts. Try again in 1 hour."]
        ↓
[Show alternatives]
```

---

## User Actions: No Soft Recovery Paths

### Control Flow Rules

**Key Loss is Irreversible:**
- ✗ No "Try again" buttons that retry the same operation
- ✗ No "Maybe later" dismissals of warnings
- ✗ No silent re-keying or automatic recovery
- ✗ No server intervention (no "contact support" with expectation of recovery)
- ✗ No cached copies of plaintext documents
- ✗ No fallback to earlier document versions from before key loss

**User Must Choose:**
- ✓ Either recover with recovery codes
- ✓ Or create a new master key (old documents lost)
- ✓ Or exit the app (documents inaccessible)
- ✓ No intermediate "continue using app with no documents" state

### Decision Points (No Dismissal)

**All key loss dialogs are BLOCKING and have no dismiss button:**

```css
/* CSS/UX Rules */
Dialog {
  role: alertdialog
  modal: true
  backdrop-close: disabled
  esc-key-dismissable: false
  click-outside-dismissable: false
  buttons: {
    primary: "Restore with Recovery Code",  /* If recovery possible */
    secondary: "Create New Master Key"      /* If recovery not possible */
    tertiary: "Exit App"                    /* If user declines both */
  }
}

/* User cannot: */
/* - Click outside dialog to close */
/* - Press ESC to dismiss */
/* - Navigate away (history.back disabled) */
/* - Close without choosing action */
```

**Message Layout:**
- ⚠️ Large warning icon
- **BOLD TITLE** with "PERMANENT" or "LOST" keywords
- Clear explanation of what happened
- Explicit statement of irreversibility
- 2-3 action buttons only (no generic close)

---

## Recovery Codes: Generation & Storage UX

### Mandatory Recovery Code Generation After Key Loss

**After ANY successful recovery or key creation:**

```
[User successfully restored UMK or created new one]
        ↓
[Display BLOCKING dialog]
        ↓
[Cannot proceed until codes are generated and acknowledged]
```

### Recovery Code Generation Dialog

**Title:** `Generate Recovery Codes Now`

**Message:**
```
⚠️  CRITICAL: Generate Recovery Codes

You must generate recovery codes now to prevent permanent data loss
if your master key is lost in the future.

WHAT ARE RECOVERY CODES?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 5 backup codes, each 8 characters
• Can restore your master key if it is ever lost
• These are your ONLY backup if you forget your password
• Without codes, data loss is permanent and irrecoverable

WHY NOW?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You just recovered or created your master key.
Generate codes now while you're thinking about it.

[Button: "Generate Codes Now"]
[Button: "I'll Do This Later" (DISABLED)]
  └─→ Button is greyed out; cannot be clicked
  └─→ User MUST generate codes to proceed
```

**After "Generate Codes" is clicked:**

```
[BLOCKING dialog: "Your Recovery Codes"]

Generated at: [timestamp]

Your codes (keep these SAFE):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CODE 1: [8 CHARS]
CODE 2: [8 CHARS]
CODE 3: [8 CHARS]
CODE 4: [8 CHARS]
CODE 5: [8 CHARS]

STORE THESE CODES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
☐ Print this page and store in a safe (fireproof location)
☐ Write by hand on paper and store offline
☐ Store in a password manager
☐ Store in a hardware security token
☐ Store with other important documents

DO NOT:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✗ Screenshot (may sync to cloud)
✗ Email to yourself
✗ Store in cloud storage (OneDrive, Google Drive, Dropbox)
✗ Share with anyone
✗ Lose them (you cannot replace them)

I HAVE SAVED MY CODES:
[Checkbox] "I have securely stored all 5 recovery codes"
[Button: "Continue to App" (DISABLED until checked)]

Alternative: [Button: "I Don't Want to Save Codes (Not Recommended)"]
├─→ User confirms: "I understand my data is at risk"
├─→ Shows warning: "Without codes, lost keys are unrecoverable"
├─→ User must check: "I accept the risk of permanent data loss"
└─→ Only then can proceed
```

### Recovery Code Management (Settings)

**In app settings, provide:**

```
Settings → Security → Recovery Codes

YOUR RECOVERY CODES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status: [✓ Codes available] [⚠️ 1 code used] [✗ All codes used]

Last generated: [date]
Codes remaining: [X of 5]

[Button: "Generate New Codes"]
  └─→ Invalidates old codes (they cannot be reused)
  └─→ Shows new codes (must acknowledge storage again)

[Button: "Download Codes (PDF)"]
  └─→ PDF with codes and storage instructions
  └─→ User can print and store offline

[Button: "View Previously Generated Codes"]
  └─→ Shows history of code generation
  └─→ Does NOT show actual codes (re-generation only way)
  └─→ Shows which codes have been used
```

---

## Server Communication: What NOT to Do

### Prohibited Server Language

**Never say to users:**

```
✗ "Contact support to recover your key"
✗ "We can help reset your password"
✗ "Call our support line for data recovery"
✗ "Submit a ticket and we'll investigate"
✗ "Try logging in again"
✗ "We may be able to recover some data"
✗ "A staff member can assist you"
✗ "This is usually recoverable"
✗ "Don't worry, we have backups"
✗ "We'll look into this for you"
```

**Why:** These suggest the server can help, which is false. Server has no keys.

### Required Server Language

**Always say to users:**

```
✓ "Rythmiq One servers do not have your master key"
✓ "No administrator can recover your key"
✓ "This loss is permanent and irrevocable"
✓ "Your only recovery option is recovery codes"
✓ "Without codes, data is permanently inaccessible"
✓ "If you lost recovery codes, data is lost"
✓ "No server-side recovery mechanism exists"
✓ "This is by design to protect your privacy"
✓ "Support cannot reverse this loss"
✓ "Your responsibility is to store recovery codes safely"
```

### Error Messages: Template

When any key loss occurs, error messages MUST follow this template:

```
[Icon: ⚠️]
[Title: "Permanent Data Loss" or "Master Key Lost"]

[Body explains:]
1. What happened (user-facing cause)
2. Why it cannot be recovered
3. Only available options
4. That server cannot help

[Buttons: Only legitimate recovery options]
```

**Example:**

```
⚠️  YOUR MASTER KEY WAS LOST

What happened:
Your master key was not found in secure storage.

Why it cannot be recovered:
The Rythmiq One server does not have your master key.
Your master key exists only on your device.
If it is lost locally, the server cannot recover it.

What you can do:
1. If you have recovery codes, use them to restore the key
2. If you don't have codes, your data is permanently inaccessible
3. You can create a new master key for future documents

Rythmiq One cannot help recover the lost key.
This loss is permanent.

[Button: "Use Recovery Code"]
[Button: "Create New Master Key"]
[Button: "Exit"]
```

---

## Edge Cases & Handling

### Case: User Has Multiple Recovery Codes; One is Compromised

**Scenario:** One recovery code was exposed in a screenshot; user wants to invalidate it

**Solution:**
```
Settings → Security → Recovery Codes
[Button: "Generate New Codes"]
  └─→ All old codes are invalidated
  └─→ 5 new codes generated
  └─→ Old codes cannot be used anymore
  └─→ User must store new codes
```

**Note:** System does NOT support invalidating individual codes; entire set must be regenerated.

### Case: User Enters Wrong Recovery Code 10 Times

**Scenario:** User is guessing or codes are wrong

**Solution:**
```
[After 3 attempts] ← Show warning
[After 5 attempts] ← Show timer (1 hour lockout)
[After 10 attempts] ← Lock recovery for 1 hour
        ↓
Display:
  "You have entered invalid codes too many times.
   Please try again in 1 hour."

[Button: "I'll Try Again Later"]
[Button: "Contact Support for Help"
  └─→ Links to FAQ about lost codes
  └─→ Does NOT promise recovery (code loss is permanent)
```

### Case: Recovery Code Is Valid But UMK Doesn't Match

**Scenario:** Code is correct, but re-derived key doesn't match stored hash (should never happen)

**This indicates either:**
1. Code was tampered with (corrupted)
2. System corruption
3. Old backup of wrong UMK

**Solution:**
```
Display:
  "⚠️  Recovery code is valid, but your master key could not be
   restored. This indicates a system problem, not a user error.

   Your data may be permanently lost due to system corruption.
   Retrying will not help.

   Contact Rythmiq One support for assistance.
   Be prepared to accept permanent data loss.

   [Button: "Exit"]
   [Button: "Contact Support"]"
```

### Case: User Loses Recovery Codes

**Scenario:** User loses all 5 recovery codes and also loses their master key

**Solution:**
```
[User enters: "I don't have recovery codes"]
        ↓
[Display: "Your data is permanently inaccessible"]
        ↓
"Without recovery codes and without your master key,
 your encrypted documents cannot be recovered through any means.

 Rythmiq One servers do not have your data or keys.
 No backup, no administrator override, no recovery service exists.

 Your data is permanently lost.

 You can create a new master key and use Rythmiq One for
 future documents. Previous documents will remain inaccessible.

 [Button: "Create New Master Key"]
 [Button: "Exit"]"
```

---

## Implementation Checklist

### Phase 1: UMK Loss (Native/Desktop)

- [ ] Detect UMK unavailable in Keychain/DPAPI/libsecret
- [ ] Display blocking warning (cannot dismiss)
- [ ] Implement recovery code entry flow
- [ ] Validate codes offline
- [ ] Restore UMK to secure storage
- [ ] Force recovery code generation after restoration
- [ ] Test with Keychain service disabled
- [ ] Test with DPAPI failures
- [ ] Test with corrupted UMK data

### Phase 2: App Reinstall

- [ ] Detect on first launch after reinstall
- [ ] Check for existing encrypted documents
- [ ] Display pre-login warning
- [ ] Implement recovery code restoration
- [ ] Implement new UMK creation
- [ ] Force recovery code generation
- [ ] Test on actual uninstall/reinstall

### Phase 3: Browser Refresh / Session Loss

- [ ] Detect session key loss on page reload
- [ ] Check if UMK exists in IndexedDB
- [ ] Implement password re-entry flow
- [ ] Implement recovery code restoration
- [ ] Detect private browsing mode
- [ ] Show private mode warning
- [ ] Test IndexedDB corruption scenarios
- [ ] Test browser cache clearing

### Phase 4: Secure Storage Failure

- [ ] Detect Keychain unavailable (macOS)
- [ ] Detect DPAPI failure (Windows)
- [ ] Detect libsecret unavailable (Linux)
- [ ] Detect IndexedDB failure (Web)
- [ ] Show platform-specific recovery instructions
- [ ] Implement recovery code path
- [ ] Test with services disabled
- [ ] Test with corrupted storage

### Phase 5: Recovery Code Management

- [ ] Generate 5 recovery codes on UMK creation
- [ ] Store code hashes securely
- [ ] Implement recovery code entry
- [ ] Validate codes offline
- [ ] Lock after N attempts
- [ ] Allow code regeneration
- [ ] Show recovery code management UI
- [ ] Export codes to PDF
- [ ] Test code validation

### Phase 6: Testing & Validation

- [ ] Test all blocking dialogs (cannot dismiss)
- [ ] Test recovery code flow
- [ ] Test invalid code handling
- [ ] Test platform-specific scenarios
- [ ] Test error messages
- [ ] Test offline functionality
- [ ] Test no server calls during key loss
- [ ] Verify no soft recovery paths
- [ ] Verify no silent re-keying

---

## Language & Messaging Standards

### Forbidden Words/Phrases

These terms must NEVER appear in key loss UX:

```
recovery     (implies the server helps)
→ Use: "restore," "recover" only if referring to recovery codes

support      (implies support can help)
→ Use: "contact support" only for non-security issues
→ Or: "Rythmiq One support cannot recover your key"

backup       (implies data is backed up)
→ Use: "recovery codes" instead
→ Data is NOT backed up on servers

temporary    (implies it can be fixed later)
→ Use: "permanent," "irrevocable"

later        (implies you can delay)
→ Say: "You must do this now"

maybe        (implies uncertainty)
→ Say: "Your data is permanently lost"

try          (implies multiple attempts will help)
→ Say: "This cannot be reversed"

help         (implies server assistance)
→ Say: "only recovery codes can help"
```

### Mandatory Words/Phrases

These terms MUST appear in key loss UX:

```
permanent          ← Appears in 100% of key loss dialogs
irreversible       ← Explains the state
cannot             ← Not "may not", not "unlikely"
no recovery        ← Absolute statement
master key         ← Specific technical term (not "password")
recovery codes     ← Only legitimate recovery mechanism
server cannot      ← Explains server limitation explicitly
by design          ← Privacy reason for no server recovery
```

### Tone & Formatting

- **Use:** Direct, clear, non-technical where possible
- **Use:** Icons (⚠️) to draw attention
- **Use:** Uppercase for critical concepts ("PERMANENT DATA LOSS")
- **Use:** Bullet points for clarity
- **Avoid:** Ambiguous language
- **Avoid:** Hope or suggestions of recovery
- **Avoid:** Jargon without explanation

---

## Summary: Control Flow Diagram

```
                    USER INITIATES ACTION
                            ↓
                    [Is UMK available?]
                        ↙      ↘
                      YES        NO
                       ↓         ↓
                   [Proceed]  [KEY LOSS DETECTED]
                       ↓         ↓
                             [Show Blocking Warning]
                                  ↓
                        ┌─────────────────────┐
                        │ Does user have      │
                        │ recovery codes?     │
                        └─────────────────────┘
                            ↙           ↘
                          YES            NO
                           ↓             ↓
                        [Enter code]  [Data Lost]
                           ↓             ↓
                        [Validate]   [Create new UMK?]
                           ↓             ↓
                        [Restore]    [YES: New setup]
                           ↓        [NO: Exit]
                        [Success]
                           ↓
                    [FORCE Gen New Codes]
                           ↓
                    [Proceed to App]
```

---

## Final Notes for Implementers

1. **All key loss dialogs are BLOCKING:** User cannot dismiss, navigate away, or close without choosing an action.

2. **No implicit recovery:** System never retries automatically or re-derives keys silently.

3. **Recovery codes are mandatory:** After any key creation/restoration, user MUST generate and store codes. Cannot proceed without acknowledgment.

4. **Server has no role:** No server calls during key loss recovery. Validation is offline. Codes are derived from key, not stored on server.

5. **Irreversibility is explicit:** Every message states that loss is permanent, irrevocable, and no server can help.

6. **User responsibility:** Recovery code storage, password security, and device security are user's responsibility. System can only enforce that warnings are shown.

7. **Test thoroughly:** All blocking dialogs, all platforms, all error cases, and all recovery paths must be tested before release.

---

*End of Document*
