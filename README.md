# InvoiceFlow – Intelligent Invoice AP Processor

An AI-assisted Accounts Payable (AP) invoice processing system that automates invoice extraction, validation, purchase order (PO) matching, duplicate detection, and decision-making.

**Live Demo:** https://zampai.vercel.app/  
**GitHub Repository:** https://github.com/Ekanshsingh22/Zampai

---

## 1. Project Overview

InvoiceFlow is an automated invoice processing application designed to simplify and improve the Accounts Payable workflow.

Traditional invoice processing involves manually checking invoice information, verifying vendors, matching purchase orders, calculating totals, and identifying duplicate submissions. These activities can be time-consuming and prone to human error.

This project provides an automated workflow that processes PDF invoices, extracts relevant information, validates invoice data, checks vendor and purchase order details, and generates an explainable processing decision.

The system classifies invoices into four categories:

- **APPROVED:** Invoice successfully passes validation.
- **REVIEW:** Invoice requires further verification.
- **HOLD:** Invoice contains missing or incomplete information.
- **REJECTED:** Invoice fails critical validation checks.

## 2. Key Features

### Automated Invoice Processing
- Upload PDF invoices through a web interface.
- Process predefined sample invoices.
- Extract invoice information from PDF documents.
- Support text-based and scanned invoice test cases.

### Invoice Validation
- Check invoice number, date, and total amount.
- Validate subtotal, tax, and total calculations.
- Identify missing or incomplete invoice information.
- Detect duplicate invoices.

### Vendor Verification
- Verify whether a vendor exists in the vendor database.
- Check vendor approval status.
- Identify blocked or unapproved vendors.

### Purchase Order Matching
- Match invoice purchase orders with available PO records.
- Verify vendor and PO consistency.
- Monitor cumulative billed amounts.
- Identify potential PO overbilling and tolerance issues.

### Decision Engine
Automatically generates one of four outcomes:

| Decision | Meaning |
|---|---|
| APPROVED | All required validation checks pass |
| REVIEW | Requires manual verification |
| HOLD | Required information is missing |
| REJECTED | Critical validation failure |

### Dashboard and Reporting
- View total processed invoices.
- Monitor approved, review, hold, and rejected invoices.
- Track purchase order utilisation.
- View invoice processing history.
- Inspect processing stages and decision reasons.

### Database Persistence
- PostgreSQL database hosted on Neon.
- Stores invoice processing history.
- Maintains records across website refreshes and deployments.

## 3. System Architecture

The application follows a simple web-based architecture.

```text
              USER
                |
                v
       Web Application
        (HTML, CSS, JS)
                |
                v
        Flask Backend
             (app.py)
                |
       +--------+---------+
       |        |         |
       v        v         v
   PDF Data   Vendor     PO
  Extraction  Checks   Matching
       |        |         |
       +--------+---------+
                |
                v
       Validation Engine
                |
                v
       Decision Generation
                |
       +--------+---------+
       |        |         |
       v        v         v
    APPROVED  REVIEW   HOLD / REJECTED
                |
                v
        PostgreSQL Database
           (Neon)
                |
                v
          Dashboard
```

## 4. Technology Stack

| Component | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, Flask |
| PDF Processing | pdfplumber |
| PDF Sample Generation | ReportLab |
| Image Processing | Pillow |
| Database | PostgreSQL |
| Database Hosting | Neon |
| Application Deployment | Vercel |
| Version Control | Git and GitHub |

## 5. Project Structure

```text
Zampai/
│
├── app.py
│   └── Flask backend and invoice processing logic
│
├── gen.py
│   └── Sample invoice generation
│
├── index.html
│   └── Frontend dashboard and user interface
│
├── requirements.txt
│   └── Python dependencies
│
├── README.md
│   └── Project documentation
│
├── data/
│   ├── vendors.csv
│   └── pos.csv
│
└── samples/
    ├── 01_happy_acme.pdf
    ├── 02_tolerance_globex.pdf
    ├── 03_split_initech_1.pdf
    ├── 04_split_initech_2.pdf
    ├── 05_duplicate_acme.pdf
    ├── 06_missing_fields.pdf
    ├── 07_blocked_umbrella.pdf
    ├── 08_over_po_acme.pdf
    ├── 09_implied_po_hooli.pdf
    └── 10_scanned_image.pdf
```

## 6. Installation and Local Setup

### Prerequisites

- Python 3.10 or later
- Git
- PostgreSQL database (or a Neon PostgreSQL connection)
- A code editor such as VS Code

### Step 1: Clone the repository

```bash
git clone https://github.com/Ekanshsingh22/Zampai.git
```

```bash
cd Zampai
```

### Step 2: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure environment variables

Configure the following environment variables:

```text
DATABASE_URL=your_neon_postgresql_connection_string
ADMIN_TOKEN=your_secure_admin_token
```

Do not commit database credentials or secret tokens to GitHub.

### Step 4: Run the application

```bash
python app.py
```

### Step 5: Open the application

Visit:

```text
http://127.0.0.1:5000
```

The application should now be accessible locally.

## 7. Sample Invoice Test Scenarios

The project includes ten predefined invoices to demonstrate different validation conditions.

| Sample | Test Scenario | Expected Outcome |
|---|---|---|
| 01_happy_acme | Valid invoice | APPROVED |
| 02_tolerance_globex | Invoice within tolerance | APPROVED |
| 03_split_initech_1 | First invoice against a shared PO | APPROVED |
| 04_split_initech_2 | Second invoice against a shared PO | APPROVED |
| 05_duplicate_acme | Duplicate invoice | REJECTED |
| 06_missing_fields | Missing invoice information | HOLD |
| 07_blocked_umbrella | Blocked vendor | REJECTED |
| 08_over_po_acme | PO overbilling | REVIEW |
| 09_implied_po_hooli | Implied PO scenario | APPROVED |
| 10_scanned_image | Scanned invoice | REVIEW |

*Note: These are the intended outcomes for the predefined demo scenarios. Actual decisions depend on the current database state and validation logic.*

## 8. Database Design

The application uses PostgreSQL to persist invoice processing history.

The main `runs` table stores information such as:

- Run ID
- Processing timestamp
- Invoice filename
- Vendor name
- Invoice number
- Invoice total
- Purchase order number
- Final processing decision
- Decision explanation
- Processing stages

Additional reference data is maintained through:

- `vendors.csv` – Vendor information and approval status.
- `pos.csv` – Purchase order information and amounts.

## 9. Deployment

The application is deployed using:

- **GitHub:** Source code management.
- **Vercel:** Web application deployment.
- **Neon:** PostgreSQL database hosting.

The Vercel project is connected to the GitHub repository. Changes committed to the repository can automatically trigger a new deployment.

### Live Application

https://zampai.vercel.app/

## 10. Future Improvements

Potential enhancements include:

- Integration with advanced AI-based invoice extraction.
- Improved OCR for scanned invoices.
- Support for multiple invoice uploads.
- Confidence scores for extracted fields.
- Human-in-the-loop approval workflows.
- Email notifications for invoices requiring review.
- Advanced analytics and financial reporting.
- Integration with ERP and accounting systems.

## 11. Conclusion

InvoiceFlow demonstrates how a structured automated workflow can simplify Accounts Payable operations.

By combining PDF extraction, invoice validation, vendor verification, purchase order matching, duplicate detection, decision generation, and database-backed reporting, the application provides a foundation for more efficient and transparent invoice processing.

The project demonstrates practical implementation of backend development, database integration, document processing, validation logic, and web application deployment.

---

**Project:** InvoiceFlow – Intelligent Invoice AP Processor  
**Case Study:** Zamp AI  
**Repository:** [Ekanshsingh22/Zampai](https://github.com/Ekanshsingh22/Zampai)  
**Live Demo:** https://zampai.vercel.app/
