import PyPDF2
import pdfplumber
import openai
import re
import config
from fpdf import FPDF
from docx import Document


openai.api_key = config.openai_api_key

#loads the PDF and extracts key text data — specifically focusing on finding merchant processor deposits.
def extract_deposits_from_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        deposits = []
        for page in pdf.pages:
            text = page.extract_text()
            # Example: Regular expression to capture common merchant processor names like Square, Stripe, etc.
            deposits.extend(re.findall(r'(Square|Stripe|Beauflor USA|PayPal|Venmo)', text))
        return deposits


#redacts sensitive information like account numbers or routing numbers
def redact_sensitive_info(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        redacted_pdf = PyPDF2.PdfWriter()
        
        for page in pdf.pages:
            text = page.extract_text()
            # Redacting account and routing numbers (very basic example)
            text = re.sub(r'\d{9}', 'REDACTED', text)  # Match routing numbers
            text = re.sub(r'\d{4} \d{4} \d{4} \d{4}', 'REDACTED', text)  # Match credit card numbers
            
            # Convert text back to page (not as simple as this, just an idea for later)
            # You’d need to actually edit the PDF to visually redact the info. This part is complex.
        
        return redacted_pdf


#create a PDF that will contain the merchant processor deposits highlighted
def create_merchant_deposit_pdf(deposits, output_filename):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.cell(200, 10, txt="Merchant Processor Deposits", ln=True, align="C")
    
    for deposit in deposits:
        pdf.cell(200, 10, txt=f"Deposit from: {deposit}", ln=True)
    
    pdf.output(output_filename)


#takes the extracted bank statement data and sends it to GPT for a summary
def generate_summary(deposits):
    # Craft your GPT prompt based on the extracted deposits
    prompt = f"Analyze the following deposits: {', '.join(deposits)}. Provide a summary of the debtor's financial habits."
    
    response = openai.Completion.create(
        engine="gpt-4",
        prompt=prompt,
        max_tokens=150,
        temperature=0.7
    )
    
    summary = response.choices[0].text.strip()
    return summary


#main function to run the script
def main(pdf_path, output_pdf, summary_filename):
    # Step 1: Extract deposits
    deposits = extract_deposits_from_pdf(pdf_path)
    
    # Step 2: Generate PDF with deposits highlighted
    create_merchant_deposit_pdf(deposits, output_pdf)
    
    # Step 3: Generate a summary using GPT-4
    summary = generate_summary(deposits)
    
    # Step 4: Save the summary to a file
    with open(summary_filename, "w") as f:
        f.write(summary)
    
    print(f"Analysis complete. Summary saved to {summary_filename} and deposits in {output_pdf}.")