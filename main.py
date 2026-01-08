from flask import Flask, request, jsonify
from flask_cors import CORS
import pdfplumber
import google.generativeai as genai
import json
import re
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Configure Gemini API
# genai.configure(api_key="AIzaSyCQnfrUOvMydYAKCilq0nV8mSZ-Ek38jGU")
genai.configure(api_key=os.environ.get("GENAI_API_KEY"))
model = genai.GenerativeModel("gemini-3-pro-preview")


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using pdfplumber"""
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    return full_text


def extract_bank_data_with_gemini(statement_text):
    """Use Gemini to extract structured data from bank statement"""
    prompt = f"""
You are an expert UK bank statement parser.
Extract information from ANY UK bank statement.
RULES:
- Account number = 8 digits
- Sort code format = XX-XX-XX
- Currency = GBP
- Identify debit vs credit automatically
- Return ONLY valid JSON
- Use null where data is missing
JSON FORMAT:
{{
  "account_number": "",
  "sort_code": "",
  "currency": "GBP",
  "transactions": [
    {{
      "date": "",
      "description": "",
      "debit": null,
      "credit": null,
      "balance": null
    }}
  ]
}}
STATEMENT TEXT:
{statement_text}
"""
    response = model.generate_content(prompt)
    return response.text


def validate_account(acc):
    """Validate account number format"""
    return bool(re.fullmatch(r"\d{8}", acc))


def validate_sort_code(code):
    """Validate sort code format"""
    return bool(re.fullmatch(r"\d{2}-\d{2}-\d{2}", code))


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "message": "API is running"}), 200


@app.route('/parse-statement', methods=['POST'])
def parse_statement():
    """
    Parse bank statement PDF and extract structured data

    Expected: multipart/form-data with 'file' field containing PDF
    Returns: JSON with account details and transactions
    """
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files['file']

        # Check if file is selected
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400

        # Check if file is allowed
        if not allowed_file(file.filename):
            return jsonify({"error": "Only PDF files are allowed"}), 400

        # Save file temporarily
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Extract text from PDF
        statement_text = extract_text_from_pdf(filepath)

        if not statement_text.strip():
            os.remove(filepath)
            return jsonify({"error": "Could not extract text from PDF"}), 400

        # Extract structured data using Gemini
        ai_output = extract_bank_data_with_gemini(statement_text)

        # Clean and parse JSON
        clean_output = ai_output.strip().replace("```json", "").replace("```", "")
        data = json.loads(clean_output)

        # Validate data
        account_valid = validate_account(data.get("account_number", ""))
        sort_code_valid = validate_sort_code(data.get("sort_code", ""))

        # Add validation results
        response_data = {
            "success": True,
            "data": data,
            "validation": {
                "account_number_valid": account_valid,
                "sort_code_valid": sort_code_valid
            },
            "extracted_text_preview": statement_text[:500]
        }

        # Clean up uploaded file
        os.remove(filepath)

        return jsonify(response_data), 200

    except json.JSONDecodeError as e:
        return jsonify({
            "error": "Failed to parse AI response as JSON",
            "details": str(e)
        }), 500
    except Exception as e:
        # Clean up file if it exists
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)

        return jsonify({
            "error": "An error occurred while processing the file",
            "details": str(e)
        }), 500


@app.route('/validate', methods=['POST'])
def validate_data():
    """
    Validate account number and sort code

    Expected JSON: {"account_number": "12345678", "sort_code": "12-34-56"}
    Returns: Validation results
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        account = data.get("account_number", "")
        sort_code = data.get("sort_code", "")

        return jsonify({
            "account_number": account,
            "account_valid": validate_account(account),
            "sort_code": sort_code,
            "sort_code_valid": validate_sort_code(sort_code)
        }), 200

    except Exception as e:
        return jsonify({
            "error": "Validation failed",
            "details": str(e)
        }), 500


if __name__ == '__main__':
    print("Starting Bank Statement Parser API...")
    print("Endpoints:")
    print("  GET  /health - Health check")
    print("  POST /parse-statement - Parse PDF bank statement")
    print("  POST /validate - Validate account number and sort code")
    app.run(debug=True, host='0.0.0.0', port=5000)