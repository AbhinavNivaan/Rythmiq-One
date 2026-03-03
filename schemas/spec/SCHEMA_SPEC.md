# Rythmiq One — Form Schema Specification

This document defines the standard JSON format for all form schemas stored in the
`form_schemas` Supabase table. Any schema file added to `schemas/` must conform to this spec.

---

## 1. File & ID Naming Convention

- File name = `{schema_id}.json`, placed in the matching type subdirectory.
- `schema_id` must be `snake_case`, start with a letter, and be globally unique.
- Pattern: `^[a-z][a-z0-9_]{2,79}$`
- Convention: `{exam_or_org}_{year}_{type}` — e.g. `neet_2026_registration`, `ssc_cgl_2026`, `passport_india_fresh`

| schema_type    | Directory                  | Example file                              |
|----------------|----------------------------|-------------------------------------------|
| `exam_form`    | `schemas/exam_forms/`      | `neet_2026_registration.json`             |
| `recruitment`  | `schemas/recruitment/`     | `ssc_cgl_2026.json`                       |
| `government_id`| `schemas/government_id/`   | `passport_india_fresh.json`               |

---

## 2. Top-Level Envelope (Required for ALL schema types)

```json
{
  "schema_id":      "neet_2026_registration",
  "schema_type":    "exam_form",
  "schema_version": "1.0.0",
  "status":         "active",

  "metadata": { ... },
  "key_dates": { ... },
  "form_sections": [ ... ],
  "document_uploads": [ ... ],
  "fee_structure": { ... }
}
```

| Field            | Type   | Required | Notes                                      |
|------------------|--------|----------|--------------------------------------------|
| `schema_id`      | string | YES      | Matches filename and DB primary key        |
| `schema_type`    | enum   | YES      | `exam_form` \| `recruitment` \| `government_id` |
| `schema_version` | string | YES      | Semantic version: `MAJOR.MINOR.PATCH`      |
| `status`         | enum   | YES      | `active` \| `inactive`                     |
| `metadata`       | object | YES      | See §3                                     |
| `key_dates`      | object | CONDITIONAL | Required for `exam_form` and `recruitment` |
| `form_sections`  | array  | YES      | See §4                                     |
| `document_uploads`| array | YES      | See §5                                     |
| `fee_structure`  | object | YES      | See §6                                     |
| `correction_window`| object | NO    | See §7 — include only if applicable        |

---

## 3. `metadata` Object

Required fields for every schema type:

```json
"metadata": {
  "display_name":    "NEET UG 2026 Registration Form",
  "short_name":      "NEET 2026",
  "conducting_body": "National Testing Agency (NTA)",
  "official_website":"https://neet.nta.nic.in",
  "category":        "medical_entrance",
  "applicable_year": 2026,
  "country":         "IN",
  "language":        "en"
}
```

| Field             | Type    | Required | Notes                                                   |
|-------------------|---------|----------|---------------------------------------------------------|
| `display_name`    | string  | YES      | Full human-readable name shown in UI                    |
| `short_name`      | string  | YES      | Compact name (e.g. shown on cards)                      |
| `conducting_body` | string  | YES      | Issuing authority / organization                        |
| `official_website`| string  | NO       | Official portal URL                                     |
| `category`        | string  | YES      | e.g. `medical_entrance`, `engineering_entrance`, `banking`, `central_govt`, `passport` |
| `applicable_year` | integer | YES      | The year this schema is valid for                       |
| `country`         | string  | NO       | ISO 3166-1 alpha-2 (default `IN`)                       |
| `language`        | string  | NO       | ISO 639-1 (default `en`)                                |

---

## 4. `key_dates` Object

Required for `exam_form` and `recruitment`. Each value is an ISO 8601 date string (`YYYY-MM-DD`).

```json
"key_dates": {
  "registration_opens":       "2026-02-08",
  "registration_closes":      "2026-03-08",
  "correction_window_start":  "2026-03-10",
  "correction_window_end":    "2026-03-12",
  "exam_date":                "2026-05-03"
}
```

All keys are optional within the object — include only the dates that are known and relevant.

---

## 5. `form_sections` Array

An ordered array of section objects. Each section groups related fields.

```json
"form_sections": [
  {
    "section_id":   "personal_details",
    "title":        "Personal Details",
    "description":  "Must match Aadhaar",
    "order":        1,
    "fields": [ ... ]
  }
]
```

### 5.1 Section Object

| Field         | Type    | Required | Notes                                  |
|---------------|---------|----------|----------------------------------------|
| `section_id`  | string  | YES      | `snake_case`, unique within schema     |
| `title`       | string  | YES      | Human-readable heading                 |
| `description` | string  | NO       | Additional guidance                    |
| `order`       | integer | YES      | 1-based display order                  |
| `fields`      | array   | YES      | Non-empty array of Field objects       |

### 5.2 Field Object

```json
{
  "field_id":    "date_of_birth",
  "label":       "Date of Birth",
  "type":        "date",
  "required":    true,
  "validation":  { "format": "DD/MM/YYYY" },
  "verification":"OTP"
}
```

| Field          | Type    | Required | Notes                                              |
|----------------|---------|----------|----------------------------------------------------|
| `field_id`     | string  | YES      | `snake_case`, unique within the schema             |
| `label`        | string  | YES      | Human-readable field name                          |
| `type`         | enum    | YES      | See §5.3                                           |
| `required`     | boolean | YES      |                                                    |
| `enum_values`  | array   | CONDITIONAL | Required when `type` is `enum`                |
| `validation`   | object  | NO       | `pattern` (regex), `format`, `minimum`, `maximum`  |
| `verification` | string  | NO       | e.g. `"OTP"` — indicates out-of-band verification  |
| `note`         | string  | NO       | Extra guidance shown to the user                   |
| `fields`       | array   | CONDITIONAL | Required when `type` is `object` — nested Field objects |

### 5.3 Valid `type` Values

| Type      | Use for                                              |
|-----------|------------------------------------------------------|
| `string`  | Free text, phone numbers, IDs                        |
| `integer` | Numeric values (year, count)                         |
| `date`    | Calendar dates — specify `format` in `validation`    |
| `boolean` | Yes/No toggles (e.g. PwD status)                     |
| `enum`    | Fixed-choice fields — must include `enum_values`     |
| `array`   | Multiple values (e.g. list of years)                 |
| `object`  | Nested group of fields — must include `fields`       |

---

## 6. `document_uploads` Array

An ordered array of document upload slot objects.

```json
"document_uploads": [
  {
    "doc_id":                   "class_10_certificate",
    "label":                    "Class 10 Certificate / Marksheet",
    "description":              "Used as Date of Birth proof",
    "allowed_formats":          ["PDF"],
    "size_min_kb":              50,
    "size_max_kb":              300,
    "required":                 true,
    "required_if":              null,
    "document_category":        "academic",
    "document_subtype":         "Class 10 Marksheet",
    "seeds_document_subtypes":  ["Class 10 Marksheet"],
    "specifications":           ["Must be a government-issued certificate"]
  }
]
```

| Field                      | Type         | Required | Notes                                                                                   |
|----------------------------|--------------|----------|-----------------------------------------------------------------------------------------|
| `doc_id`                   | string       | YES      | `snake_case`, unique within schema                                                      |
| `label`                    | string       | YES      | Human-readable name                                                                     |
| `description`              | string       | NO       | Extra context                                                                           |
| `allowed_formats`          | array        | YES      | Non-empty. Values: `"PDF"`, `"JPG"`, `"JPEG"`, `"PNG"`                                 |
| `size_min_kb`              | integer      | NO       | Minimum file size in KB                                                                 |
| `size_max_kb`              | integer      | YES      | Maximum file size in KB                                                                 |
| `required`                 | boolean      | YES      |                                                                                         |
| `required_if`              | string\|null | NO       | Condition string, e.g. `"pwd_pwbd_status == true"`. Uses `field_id == value` syntax. `null` if unconditional. |
| `specifications`           | array        | NO       | Human-readable bullet-point guidelines                                                  |
| `document_category`        | string       | NO       | Vault category this upload maps to. One of: `identity`, `academic`, `address`, `financial`, `photograph`, `signature`, `certificate`, `other`. Omit only for uploads with no vault equivalent (e.g. thumb impressions). |
| `document_subtype`         | string       | NO       | The exact vault document subtype required for this slot. Must be a value present in the upload UI's type list for the category (after seeding). |
| `seeds_document_subtypes`  | array        | NO       | Portal-specific subtypes to inject into the upload UI for this category. **Required whenever `document_subtype` is a non-standard value** (i.e. not already in the base type list). Example: `["Postcard Photo"]` for photograph, `["Class 10 Marksheet"]` for academic. Without this, users will not see the subtype as an option when labelling their upload. |

### 6.1 Vault-mapping fields

`document_category`, `document_subtype`, and `seeds_document_subtypes` together tell the mobile app how to link a portal's document requirement to a file the user has stored in their vault.

**How it works:**
1. On the Upload (Create Master) screen the app fetches all active form schemas and merges their `seeds_document_subtypes` into the base type lists per category. This makes portal-specific subtypes selectable even if they were not in the built-in defaults.
2. When a user selects a category and subtype, the stored `document_category` + `document_subtype` on the master document are used during the Export flow to match that document against the portal's requirement.

**Rule of thumb:** Add `seeds_document_subtypes` whenever `document_subtype` is a non-standard value. Standard values (already in the base lists) do not need seeding:
- `photograph`: Passport Photo, Profile Photo, ID Photo, Document Photo
- `signature`: Personal Signature
- `academic`: Certificate, Diploma, Degree, Transcript, Grade Card
- `identity`: Aadhaar Card, PAN Card, Passport, Voter ID, Driving Licence, Ration Card

---

## 7. `fee_structure` Object

```json
"fee_structure": {
  "currency":      "INR",
  "payment_modes": ["Net Banking", "UPI", "Credit Card", "Debit Card"],
  "tiers": [
    { "category": "General",  "amount": 1700 },
    { "category": "OBC-NCL",  "amount": 1600 },
    { "category": "SC",       "amount": 1000 }
  ]
}
```

| Field           | Type   | Required | Notes                            |
|-----------------|--------|----------|----------------------------------|
| `currency`      | string | YES      | ISO 4217 code (e.g. `INR`)       |
| `payment_modes` | array  | YES      | Non-empty                        |
| `tiers`         | array  | YES      | Each item has `category` and `amount` (integer, in smallest unit if needed) |

---

## 8. `correction_window` Object (Optional)

Include only if the schema has an official correction/edit window.

```json
"correction_window": {
  "editable_field_ids":     ["full_name", "date_of_birth", "gender"],
  "non_editable_field_ids": ["aadhaar_number", "email_id"],
  "correction_fee":         null,
  "notes": ["Corrections allowed only once", "No offline correction requests entertained"]
}
```

| Field                    | Type         | Required | Notes                                            |
|--------------------------|--------------|----------|--------------------------------------------------|
| `editable_field_ids`     | array        | YES      | Each value must be a `field_id` defined in `form_sections` |
| `non_editable_field_ids` | array        | YES      | Same constraint                                  |
| `correction_fee`         | integer\|null | NO      | Fee in currency units; `null` if free            |
| `notes`                  | array        | NO       | Human-readable caveats                           |

---

## 9. Required Sections by `schema_type`

| Section             | `exam_form` | `recruitment` | `government_id` |
|---------------------|:-----------:|:-------------:|:---------------:|
| `metadata`          | Required    | Required      | Required        |
| `key_dates`         | Required    | Required      | Optional        |
| `form_sections`     | Required    | Required      | Required        |
| `document_uploads`  | Required    | Required      | Required        |
| `fee_structure`     | Required    | Required      | Required        |
| `correction_window` | Optional    | Optional      | Optional        |

---

## 10. Versioning Policy

- Increment `PATCH` (e.g. `1.0.0` → `1.0.1`) for corrections to existing field labels, adding `note` fields, fixing fee amounts.
- Increment `MINOR` (e.g. `1.0.0` → `1.1.0`) for adding new optional fields or document slots.
- Increment `MAJOR` (e.g. `1.0.0` → `2.0.0`) for structural changes — adding/removing required fields, changing `schema_type`, renaming `section_id` or `field_id` values.

When a new version is injected, the old version row remains in the database with `is_active = false` for audit purposes. Only one version per `schema_id` should be `is_active = true` at any time.
