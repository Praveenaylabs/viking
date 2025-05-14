from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, json, session , send_file ,Response 
import pymysql
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from mysql.connector import Error
from datetime import datetime, timedelta
import traceback
import json  # ✅ Use Python’s built-in json module
import string
import os
from werkzeug.utils import secure_filename
from flask import send_from_directory
from datetime import datetime




app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session management
app.permanent_session_lifetime = timedelta(minutes=60) # Auto logout after 30 minutes of inactivity
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ✅ Ensure the folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])  

# Database Connection Function
def get_db_connection():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="Money2035",
        database="leads",
        cursorclass=pymysql.cursors.DictCursor  # Ensures dictionary output

    )

# User Authentication Data
users = {
    'admin': {'username': 'admin', 'password': 'admin123', 'role': 'admin'},
    'emp': {'username': 'emp', 'password': 'emp123', 'role': 'emp'},
}

# 🔹 Decorator for Login Protection
def login_required(f):
    def wrap(*args, **kwargs):
        if 'username' not in session:
            flash("⚠️ You must log in first!", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap



@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            connection = get_db_connection()
            cursor = connection.cursor(pymysql.cursors.DictCursor)

            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()

            if user:
                stored_password = user['password']

                # Check hashed password
                if check_password_hash(stored_password, password):
                    session.permanent = True
                    session['user_id'] = user['id']
                    session['username'] = user['username']

                    flash('Login successful!', 'success')

                    if 'role' in user and user['role'] == 'Admin':
                        return redirect(url_for('admindash'))
                    return redirect(url_for('empdash'))

                else:
                    flash('Invalid username or password', 'error')
            else:
                flash('Invalid username or password', 'error')

        except Exception as e:
            flash('An error occurred while logging in', 'error')
            print(f"Error: {e}")

        finally:
            cursor.close()
            connection.close()

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()  # Clear session data
    flash("Logged out successfully!", "success")
    return redirect(url_for('login'))





    
@app.route('/reportCER')
@login_required
def reportCER():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Fetch all reports
        cursor.execute("SELECT CertificateNumber, date, applicant_name, shipper, consignee, total_pkgs ,status, sb_number FROM cer")
        cer_data = cursor.fetchall()

        conn.close()

        return render_template('reportCER.html', cer_data=cer_data)
    except Exception as e:
        print(f"Error: {e}")
        flash('An error occurred while fetching the reports.', 'error')
        return redirect(url_for('reportCER'))
    
@app.route('/delete-certificates', methods=['POST'])  # Removed <int:certificate_ids> from URL
@login_required
def delete_certificates():
    try:
        data = request.get_json()
        certificate_ids = data.get('ids', [])

        if not certificate_ids:
            return jsonify({"error": "No certificate IDs provided"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure there are IDs to delete
        if certificate_ids:
            format_strings = ','.join(['%s'] * len(certificate_ids))
            query = f"DELETE FROM cer WHERE CertificateNumber IN ({format_strings})"
            cursor.execute(query, tuple(certificate_ids))
            conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"message": "Certificates deleted successfully"}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": "An error occurred while deleting certificates"}), 500
       
@app.route('/delete_cer/<int:certificate_number>', methods=['POST'])
@login_required
def delete_cer(certificate_number):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete the record
        cursor.execute("DELETE FROM cer WHERE CertificateNumber = %s", (certificate_number,))
        conn.commit()

        conn.close()
        flash('Certificate deleted successfully.', 'success')
    except Exception as e:
        print(f"Error: {e}")
        flash('An error occurred while deleting the certificate.', 'error')

    return redirect(url_for('reportCER'))

@app.route('/reportCER1/<int:CertificateNumber>')
@login_required
def reportCER1(CertificateNumber):  # This must match url_for('reportCER1')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Fetch the certificate details
        cursor.execute("SELECT * FROM cer WHERE CertificateNumber = %s", (CertificateNumber,))
        cer_details = cursor.fetchone()

        conn.close()

        if not cer_details:
            flash("No record found for the given Certificate Number.", "error")
            return redirect(url_for("reportCER"))

        # Convert survey_data from JSON (if available)
        survey_data = []
        if cer_details.get('survey_data'):  
            try:
                survey_data = json.loads(cer_details['survey_data'])
            except json.JSONDecodeError:
                flash("Error processing survey data.", "error")

        return render_template('reportCER1.html', cer=cer_details, survey_data=survey_data)

    except Exception as e:
        print(f"Error fetching report: {e}")
        flash("An error occurred while fetching the report.", "error")
        return redirect(url_for("reportCER"))


    

#####################################################################
#                 <--- Admin Certificate --->                       #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
##########################START######################################

@app.route('/get_latest_certificate')
@login_required
def get_latest_certificate():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT CertificateNumber, status FROM cer ORDER BY id DESC LIMIT 1")
                certificate_data = cursor.fetchone()

        if not certificate_data:
            certificate_data = {"CertificateNumber": "N/A", "status": "Unknown"}

    except Exception as e:
        print(f"Error fetching latest certificate: {e}")
        certificate_data = {"CertificateNumber": "Error", "status": "Error"}

    return jsonify(certificate_data)


@app.route('/certificate')
@login_required
def certificate():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                conn.begin()

                # Get the current Year-Month (YYYYMM)
                current_year_month = datetime.now().strftime("%Y%m")

                # 🔹 Fetch the latest certificate
                cursor.execute("SELECT CertificateNumber FROM cer ORDER BY id DESC LIMIT 1 FOR UPDATE")
                last_record = cursor.fetchone()

                if last_record and last_record["CertificateNumber"]:
                    last_certificate = last_record["CertificateNumber"]
                    last_year_month = last_certificate[:6]  # Extract YYYYMM

                    if last_year_month == current_year_month:
                        last_number = int(last_certificate[6:])  # Extract numeric part
                        next_number = last_number + 1
                    else:
                        next_number = 1  # Reset numbering for new month/year
                else:
                    next_number = 1  # Start fresh if no records exist

                # 🔹 Generate new Certificate Number
                new_certificate_number = f"{current_year_month}{str(next_number).zfill(6)}"

                # Insert new certificate with status "Open"
                cursor.execute("INSERT INTO cer (CertificateNumber, status) VALUES (%s, %s)", 
                               (new_certificate_number, "Open"))
                conn.commit()

                # Prepare data to send to template
                certificate_data = {"CertificateNumber": new_certificate_number, "status": "Open"}

        return render_template('certificate.html', certificate=certificate_data)

    except Exception as e:
        conn.rollback()  # Rollback if there's an error
        print(f"Error generating certificate: {e}")
        return "Error generating certificate", 500

    
#CER    
@app.route('/submit_cer', methods=['POST'])
@login_required
def submit_cer():
    try:
        # Extract form data
        certificate_number = request.form.get('CertificateNumber', '').strip()
        date = request.form.get('date', '').strip()
        applicant_name = request.form.get('applicantName', '').strip()
        shipper = request.form.get('shipper', '').strip()
        consignee = request.form.get('consignee', '').strip()
        commodity = request.form.get('commodity', '').strip()
        port_of_discharge = request.form.get('portOfDischarge', '').strip()
        sb_number = request.form.get('sb_number', '').strip()
        cf_agent = request.form.get('cf_agent', '').strip()
        type_of_packing = request.form.get('type_of_packing', '').strip()  # ✅ Added Type of Packing
        action = request.form.get('action')  # Determine if saving as draft or submitting

        # Helper function to safely convert values to float
        def safe_float(value):
            try:
                return float(value) if value.strip() else None  # Return None if empty
            except ValueError:
                return None

        quantity = safe_float(request.form.get('quantity', ''))
        gross_weight = safe_float(request.form.get('gross_weight', ''))

        # Collect survey data
        survey_data = []
        rows = len(request.form.getlist('marksNos[]'))
        for i in range(rows):
            marks_no = request.form.getlist('marksNos[]')[i].strip() or None
            no_of_pkgs = (
                int(request.form.getlist('noOfPkgs[]')[i])
                if request.form.getlist('noOfPkgs[]')[i].strip()
                else None
            )
            length = safe_float(request.form.getlist('length[]')[i])
            breadth = safe_float(request.form.getlist('breadth[]')[i])
            height = safe_float(request.form.getlist('height[]')[i])
            volume_unit = safe_float(request.form.getlist('volumeUnit[]')[i])
            volume_cum = safe_float(request.form.getlist('volumePerUnit[]')[i])

            survey_data.append({
                'marks_no': marks_no,
                'no_of_pkgs': no_of_pkgs,
                'length': length,
                'breadth': breadth,
                'height': height,
                'volume_unit': volume_unit,
                'volumePerUnit': volume_cum,
            })

        # Get total volume and total packages from frontend
        total_volume = safe_float(request.form.get('totalVolume', ''))
        total_pkgs = safe_float(request.form.get('totalPkgs', ''))

        survey_data_json = json.dumps(survey_data)

        # Determine status: Draft or In Progress
        status = "Draft" if action == "Save as Draft" else "In Progress"

        # Required field validation only when submitting (not for draft)
        if status == "In Progress":
            required_fields = {
                "Certificate Number": certificate_number,
                "Date": date,
                "Applicant Name": applicant_name,
                "Shipper": shipper,
                "Consignee": consignee,
                "Commodity": commodity,
                "Port of Discharge": port_of_discharge,
                "Surveyor": cf_agent,
            }
            for field, value in required_fields.items():
                if not value:
                    flash(f"Error: {field} is required!", "error")
                    return redirect(url_for('forms'))

        # Database Operations
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT CertificateNumber FROM cer WHERE CertificateNumber = %s",
                    (certificate_number,),
                )
                exists = cursor.fetchone()

                if exists:
                    # Update existing record
                    update_query = """
                        UPDATE cer SET 
                            date = %s, applicant_name = %s, shipper = %s, consignee = %s, 
                            commodity = %s, port_of_discharge = %s, sb_number = %s, quantity = %s, 
                            gross_weight = %s, cf_agent = %s, type_of_packing = %s,
                            total_volume = %s, total_pkgs = %s, survey_data = %s, status = %s
                        WHERE CertificateNumber = %s
                    """
                    cursor.execute(
                        update_query,
                        (
                            date,
                            applicant_name,
                            shipper,
                            consignee,
                            commodity,
                            port_of_discharge,
                            sb_number,
                            quantity,
                            gross_weight,
                            cf_agent,
                            type_of_packing,
                            total_volume,
                            total_pkgs,
                            survey_data_json,
                            status,
                            certificate_number,
                        ),
                    )
                else:
                    flash("Error: Certificate number not found in the database.", "error")
                    return redirect(url_for('forms'))

                conn.commit()

        # Flash message for success
        flash(
            'Form saved as draft!' if status == "Draft" else 'Form submitted successfully!',
            'success',
        )

        # Redirect based on action
        if action == "Submit and New":
            return redirect(url_for('certificate'))  # Redirect to new entry form
        
        return redirect(url_for('forms'))  # Default redirect to forms page

    except Exception as e:
        print(f"Error: {e}")
        flash(f'An error occurred while processing the form. Error: {e}', 'error')
        return redirect(url_for('forms'))



@app.route('/certificateedit')
@login_required
def certificateedit():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                
                # Fetch all certificate records
                cursor.execute("""
                    SELECT CertificateNumber, date, applicant_name, shipper, consignee, total_pkgs, status 
                    FROM cer
                """)
                cer_data = cursor.fetchall()

        return render_template('certificateedit.html', cer_data=cer_data)
    
    except Exception as e:
        print(f"Error fetching certificate records: {e}")
        flash("An error occurred while fetching the certificate records.", "error")
        return redirect(url_for("admindash"))

@app.route('/certificateedit1/<int:CertificateNumber>')
@login_required
def certificateedit1(CertificateNumber):
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                print(f"Fetching CertificateNumber: {CertificateNumber}")  # Debug Print

                cursor.execute("SELECT * FROM cer WHERE CertificateNumber = %s", (CertificateNumber,))
                certificate_details = cursor.fetchone()

                if not certificate_details:
                    flash("No record found for the given Certificate Number.", "error")
                    return redirect(url_for("certificateedit"))  # ✅ Fixed redirect

                print("Certificate Details:", certificate_details)  # Debug Print

                return render_template('certificateedit1.html', certificate=certificate_details)

    except Exception as e:
        print(f"Error fetching certificate details: {e}")
        flash("An error occurred while fetching certificate details.", "error")
        return redirect(url_for("certificateedit"))  # ✅ Fixed redirect
    
@app.route('/update_certificatead/<int:CertificateNumber>', methods=['POST'])
@login_required
def update_certificatead(CertificateNumber):
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                
                # Extract form data
                form_data = {key: request.form.get(key, '').strip() for key in [
                    "date", "applicant_name", "shipper", "consignee", "commodity", 
                    "port_of_discharge", "sb_number", "cf_agent"
                ]}

                # Safely parse numerical fields
                def safe_float(value):
                    try:
                        return float(value) if value.strip() else None
                    except ValueError:
                        return None

                quantity = safe_float(request.form.get('quantity', ''))
                gross_weight = safe_float(request.form.get('gross_weight', ''))

                # Validate required fields
                for field, value in form_data.items():
                    if not value:
                        flash(f"Error: {field.replace('_', ' ').title()} is required!", "error")
                        return redirect(url_for('certificateedit1', CertificateNumber=CertificateNumber))

                # Process checkbox values (survey measure data)
                survey_data = []
                marksNos = request.form.getlist('marksNos[]')
                noOfPkgs = request.form.getlist('noOfPkgs[]')
                lengths = request.form.getlist('length[]')
                breadths = request.form.getlist('breadth[]')
                heights = request.form.getlist('height[]')
                volumeUnits = request.form.getlist('volumeUnit[]')

                for i in range(len(marksNos)):
                    try:
                        volume = safe_float(lengths[i]) * safe_float(breadths[i]) * safe_float(heights[i]) if all([lengths[i], breadths[i], heights[i]]) else None
                        volume_cum = safe_float(volumeUnits[i]) * volume if volume and safe_float(volumeUnits[i]) else None

                        survey_data.append({
                            'marks_no': marksNos[i].strip() or None,
                            'no_of_pkgs': int(noOfPkgs[i]) if noOfPkgs[i].strip() else None,
                            'length': safe_float(lengths[i]),
                            'breadth': safe_float(breadths[i]),
                            'height': safe_float(heights[i]),
                            'volume': volume,
                            'volume_unit': safe_float(volumeUnits[i]),
                            'volume_cum': volume_cum
                        })
                    except Exception as e:
                        print(f"Error processing survey data: {e}")

                total_volume = sum(row['volume'] for row in survey_data if row['volume'] is not None)
                total_pkgs = sum(row['no_of_pkgs'] for row in survey_data if row['no_of_pkgs'] is not None)

                # Serialize survey data as JSON
                survey_data_json = json.dumps(survey_data)

                # ✅ Update certificate record
                update_query = """
                    UPDATE cer 
                    SET 
                        date = %s, applicant_name = %s, shipper = %s, consignee = %s, 
                        commodity = %s, port_of_discharge = %s, sb_number = %s, quantity = %s, 
                        gross_weight = %s, cf_agent = %s,
                        total_volume = %s, total_pkgs = %s, survey_data = %s, status = 'In Progress'
                    WHERE CertificateNumber = %s
                """
                values = (
                    form_data["date"], form_data["applicant_name"], form_data["shipper"], form_data["consignee"], 
                    form_data["commodity"], form_data["port_of_discharge"], form_data["sb_number"], 
                    quantity, gross_weight, form_data["cf_agent"],
                    total_volume, total_pkgs, survey_data_json, CertificateNumber
                )

                cursor.execute(update_query, values)
                conn.commit()
                print(f"Received data: {request.form.to_dict()}")

                flash('Certificate updated successfully!', 'success')
                return redirect(url_for('admindash'))

    except Exception as e:
        print(f"Error: {e}")
        flash(f'An error occurred: {e}', 'error')
        return redirect(url_for('admindash'))
@app.route('/certificate_excel')
@login_required
def certificate_excel():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                
                # Fetch all certificate records
                cursor.execute("select * from cer")
                cer_data = cursor.fetchall()

        return render_template('certificate_excel.html', cer_data=cer_data)
    
    except Exception as e:
        print(f"Error fetching certificate records: {e}")
        flash("An error occurred while fetching the certificate records.", "error")
        return redirect(url_for("admindash"))
#####################################################################
#               <--- Admin Certificate--->                          #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
#####################################################################


#####################################################################
#              <--- Employee Certificate --->                       #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
#####################################################################

@app.route('/empcertificate')
@login_required
def empcertificate():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                conn.begin()

                # Get the current Year-Month (YYYYMM)
                current_year_month = datetime.now().strftime("%Y%m")

                # 🔹 Fetch the latest certificate
                cursor.execute("SELECT CertificateNumber FROM cer ORDER BY id DESC LIMIT 1 FOR UPDATE")
                last_record = cursor.fetchone()

                if last_record and last_record["CertificateNumber"]:
                    last_certificate = last_record["CertificateNumber"]
                    last_year_month = last_certificate[:6]  # Extract YYYYMM

                    if last_year_month == current_year_month:
                        last_number = int(last_certificate[6:])  # Extract numeric part
                        next_number = last_number + 1
                    else:
                        next_number = 1  # Reset numbering for new month/year
                else:
                    next_number = 1  # Start fresh if no records exist

                # 🔹 Generate new Certificate Number
                new_certificate_number = f"{current_year_month}{str(next_number).zfill(6)}"

                # Insert new certificate with status "Open"
                cursor.execute("INSERT INTO cer (CertificateNumber, status) VALUES (%s, %s)", 
                               (new_certificate_number, "Open"))
                conn.commit()

                # Prepare data to send to template
                certificate_data = {"CertificateNumber": new_certificate_number, "status": "Open"}

        return render_template('empcertificate.html', certificate=certificate_data)

    except Exception as e:
        conn.rollback()  # Rollback if there's an error
        print(f"Error generating certificate: {e}")
        return "Error generating certificate", 500

@app.route('/submit_cerem', methods=['POST'])
@login_required
def submit_cerem():
    try:
        # Extract form data
        certificate_number = request.form.get('CertificateNumber', '').strip()
        date = request.form.get('date', '').strip()
        applicant_name = request.form.get('applicantName', '').strip()
        shipper = request.form.get('shipper', '').strip()
        consignee = request.form.get('consignee', '').strip()
        commodity = request.form.get('commodity', '').strip()
        port_of_discharge = request.form.get('portOfDischarge', '').strip()
        sb_number = request.form.get('sb_number', '').strip()
        cf_agent = request.form.get('cf_agent', '').strip()
        type_of_packing = request.form.get('type_of_packing', '').strip()  # ✅ Added Type of Packing
        action = request.form.get('action')  # Determine if saving as draft or submitting

        # Helper function to safely convert values to float
        def safe_float(value):
            try:
                return float(value) if value.strip() else None  # Return None if empty
            except ValueError:
                return None

        quantity = safe_float(request.form.get('quantity', ''))
        gross_weight = safe_float(request.form.get('gross_weight', ''))

        # Collect survey data
        survey_data = []
        rows = len(request.form.getlist('marksNos[]'))
        for i in range(rows):
            marks_no = request.form.getlist('marksNos[]')[i].strip() or None
            no_of_pkgs = (
                int(request.form.getlist('noOfPkgs[]')[i])
                if request.form.getlist('noOfPkgs[]')[i].strip()
                else None
            )
            length = safe_float(request.form.getlist('length[]')[i])
            breadth = safe_float(request.form.getlist('breadth[]')[i])
            height = safe_float(request.form.getlist('height[]')[i])
            volume_unit = safe_float(request.form.getlist('volumeUnit[]')[i])
            volume_cum = safe_float(request.form.getlist('volumePerUnit[]')[i])

            survey_data.append({
                'marks_no': marks_no,
                'no_of_pkgs': no_of_pkgs,
                'length': length,
                'breadth': breadth,
                'height': height,
                'volume_unit': volume_unit,
                'volumePerUnit': volume_cum,
            })

        # Get total volume and total packages from frontend
        total_volume = safe_float(request.form.get('totalVolume', ''))
        total_pkgs = safe_float(request.form.get('totalPkgs', ''))

        survey_data_json = json.dumps(survey_data)

        # Determine status: Draft or In Progress
        status = "Draft" if action == "Save as Draft" else "In Progress"

        # Required field validation only when submitting (not for draft)
        if status == "In Progress":
            required_fields = {
                "Certificate Number": certificate_number,
                "Date": date,
                "Applicant Name": applicant_name,
                "Shipper": shipper,
                "Consignee": consignee,
                "Commodity": commodity,
                "Port of Discharge": port_of_discharge,
                "Surveyor": cf_agent,
            }
            for field, value in required_fields.items():
                if not value:
                    flash(f"Error: {field} is required!", "error")
                    return redirect(url_for('forms'))

        # Database Operations
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT CertificateNumber FROM cer WHERE CertificateNumber = %s",
                    (certificate_number,),
                )
                exists = cursor.fetchone()

                if exists:
                    # Update existing record
                    update_query = """
                        UPDATE cer SET 
                            date = %s, applicant_name = %s, shipper = %s, consignee = %s, 
                            commodity = %s, port_of_discharge = %s, sb_number = %s, quantity = %s, 
                            gross_weight = %s, cf_agent = %s, type_of_packing = %s,
                            total_volume = %s, total_pkgs = %s, survey_data = %s, status = %s
                        WHERE CertificateNumber = %s
                    """
                    cursor.execute(
                        update_query,
                        (
                            date,
                            applicant_name,
                            shipper,
                            consignee,
                            commodity,
                            port_of_discharge,
                            sb_number,
                            quantity,
                            gross_weight,
                            cf_agent,
                            type_of_packing,
                            total_volume,
                            total_pkgs,
                            survey_data_json,
                            status,
                            certificate_number,
                        ),
                    )
                else:
                    flash("Error: Certificate number not found in the database.", "error")
                    return redirect(url_for('forms'))

                conn.commit()

        # Flash message for success
        flash(
            'Form saved as draft!' if status == "Draft" else 'Form submitted successfully!',
            'success',
        )

        # ✅ Redirect based on action
        if action == "Submit and New":
            return redirect(url_for('empcertificate'))  # Redirect to form for new entry
        
        return redirect(url_for('empforms'))  # Default redirect to forms page

    except Exception as e:
        print(f"Error: {e}")
        flash(f'An error occurred while processing the form. Error: {e}', 'error')
        return redirect(url_for('empforms'))

    
@app.route('/empcertificateedit')
@login_required
def empcertificateedit():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                
                # Fetch all certificate records
                cursor.execute("""
                    SELECT CertificateNumber, date, applicant_name, shipper, consignee, total_pkgs, status 
                    FROM cer
                """)
                cer_data = cursor.fetchall()

        return render_template('empcertificateedit.html', cer_data=cer_data)
    
    except Exception as e:
        print(f"Error fetching certificate records: {e}")
        flash("An error occurred while fetching the certificate records.", "error")
        return redirect(url_for("empdash"))



@app.route('/empcertificateedit1/<int:CertificateNumber>')
@login_required
def empcertificateedit1(CertificateNumber):
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                print(f"Fetching CertificateNumber: {CertificateNumber}")  # Debug Print

                cursor.execute("SELECT * FROM cer WHERE CertificateNumber = %s", (CertificateNumber,))
                certificate_details = cursor.fetchone()

                if not certificate_details:
                    flash("No record found for the given Certificate Number.", "error")
                    return redirect(url_for("empcertificateedit"))  # ✅ Fixed redirect

                print("Certificate Details:", certificate_details)  # Debug Print

                return render_template('empcertificateedit1.html', certificate=certificate_details)

    except Exception as e:
        print(f"Error fetching certificate details: {e}")
        flash("An error occurred while fetching certificate details.", "error")
        return redirect(url_for("empcertificateedit"))  # ✅ Fixed redirect




@app.route('/update_certificate/<int:CertificateNumber>', methods=['POST'])
@login_required
def update_certificate(CertificateNumber):
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                
                # Extract form data
                form_data = {key: request.form.get(key, '').strip() for key in [
                    "date", "applicant_name", "shipper", "consignee", "commodity", 
                    "port_of_discharge", "sb_number", "cf_agent"
                ]}

                # Safely parse numerical fields
                def safe_float(value):
                    try:
                        return float(value) if value.strip() else None
                    except ValueError:
                        return None

                quantity = safe_float(request.form.get('quantity', ''))
                gross_weight = safe_float(request.form.get('gross_weight', ''))

                # Validate required fields
                for field, value in form_data.items():
                    if not value:
                        flash(f"Error: {field.replace('_', ' ').title()} is required!", "error")
                        return redirect(url_for('empcertificateedit1', CertificateNumber=CertificateNumber))

                # Process checkbox values (survey measure data)
                survey_data = []
                marksNos = request.form.getlist('marksNos[]')
                noOfPkgs = request.form.getlist('noOfPkgs[]')
                lengths = request.form.getlist('length[]')
                breadths = request.form.getlist('breadth[]')
                heights = request.form.getlist('height[]')
                volumeUnits = request.form.getlist('volumeUnit[]')

                for i in range(len(marksNos)):
                    try:
                        volume = safe_float(lengths[i]) * safe_float(breadths[i]) * safe_float(heights[i]) if all([lengths[i], breadths[i], heights[i]]) else None
                        volume_cum = safe_float(volumeUnits[i]) * volume if volume and safe_float(volumeUnits[i]) else None

                        survey_data.append({
                            'marks_no': marksNos[i].strip() or None,
                            'no_of_pkgs': int(noOfPkgs[i]) if noOfPkgs[i].strip() else None,
                            'length': safe_float(lengths[i]),
                            'breadth': safe_float(breadths[i]),
                            'height': safe_float(heights[i]),
                            'volume': volume,
                            'volume_unit': safe_float(volumeUnits[i]),
                            'volume_cum': volume_cum
                        })
                    except Exception as e:
                        print(f"Error processing survey data: {e}")

                total_volume = sum(row['volume'] for row in survey_data if row['volume'] is not None)
                total_pkgs = sum(row['no_of_pkgs'] for row in survey_data if row['no_of_pkgs'] is not None)

                # Serialize survey data as JSON
                survey_data_json = json.dumps(survey_data)

                # ✅ Update certificate record
                update_query = """
                    UPDATE cer 
                    SET 
                        date = %s, applicant_name = %s, shipper = %s, consignee = %s, 
                        commodity = %s, port_of_discharge = %s, sb_number = %s, quantity = %s, 
                        gross_weight = %s, cf_agent = %s, 
                        total_volume = %s, total_pkgs = %s, survey_data = %s, status = 'In Progress'
                    WHERE CertificateNumber = %s
                """
                values = (
                    form_data["date"], form_data["applicant_name"], form_data["shipper"], form_data["consignee"], 
                    form_data["commodity"], form_data["port_of_discharge"], form_data["sb_number"], 
                    quantity, gross_weight, form_data["cf_agent"],
                    total_volume, total_pkgs, survey_data_json, CertificateNumber
                )

                cursor.execute(update_query, values)
                conn.commit()
                print(f"Received data: {request.form.to_dict()}")

                flash('Certificate updated successfully!', 'success')
                return redirect(url_for('empdash'))

    except Exception as e:
        print(f"Error: {e}")
        flash(f'An error occurred: {e}', 'error')
        return redirect(url_for('empdash'))
    
#####################################################################
#              <--- Employee Certificate --->                       #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
#####################################################################
@app.route('/excel_dash')
@login_required
def excel_dash():
    return render_template('excel_dash.html')


@app.route('/emp_excel')
@login_required
def emp_excel():

    try:
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Fetch relevant data from the `form` table
        cursor.execute("SELECT * FROM form")
        form = cursor.fetchall()

        conn.close()

        # Pass the data to the report.html template
        return render_template('emp_excel.html', form=form)
    except Error as e:
        print(f"Error: {e}")
        flash('An error occurred while fetching the reports. Please try again.', 'error')
        return render_template('emp_excel.html')

@app.route('/container_excel')
@login_required
def container_excel():     
 
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Fetch all container records
        cursor.execute("SELECT * FROM container")
        container_data = cursor.fetchall()

        conn.close()

        return render_template('container_excel.html', container_data=container_data)
    except Exception as e:
        print(f"Error: {e}")
        flash('An error occurred while fetching the container records.', 'error')
        return redirect(url_for('container_excel'))



@app.route('/admindash')
@login_required
def admindash():

        
    return render_template('admindash.html')

@app.route('/cont')
@login_required
def cont():
    if session.get('role') != 'admin':
        flash("Unauthorized access!", "error")
    return render_template('cont.html')

@app.route('/contrpt')
@login_required
def contrpt():
    return render_template('contrpt.html')

@app.route('/empformsonm')
@login_required
def empformsonm():
    return render_template('empformsonm.html')




@app.route('/empforms')
@login_required
def empforms():
    return render_template('empforms.html')
    

@app.route('/empdash')
@login_required
def empdash():
    return render_template('empdash.html')




#####################################################################
#                 <--- Admin Container--->                          #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
#########################START#######################################

#####################################################################
#                <--- Admin Container Rpt.no --->                   #
#####################################################################
@app.route('/get_latest_certificate122')
@login_required
def get_latest_certificate122():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT CertificateNumber, status FROM container ORDER BY id DESC LIMIT 1")
                certificate_data = cursor.fetchone()

        if not certificate_data:
            certificate_data = {"CertificateNumber": "N/A", "status": "Unknown"}

    except Exception as e:
        print(f"Error fetching latest certificate: {e}")
        certificate_data = {"CertificateNumber": "Error", "status": "Error"}

    return jsonify(certificate_data)



@app.route('/container')
@login_required
def container():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                conn.begin()

                # Get the last certificate number
                cursor.execute("SELECT CertificateNumber FROM container ORDER BY id DESC LIMIT 1 FOR UPDATE")
                last_record = cursor.fetchone()

                if last_record and last_record["CertificateNumber"].isdigit():
                    next_number = int(last_record["CertificateNumber"]) + 1
                else:
                    next_number = 1  # Start from 1 if no records exist

                new_certificate_number = str(next_number)

                # Insert new certificate
                insert_query = "INSERT INTO container (CertificateNumber, status) VALUES (%s, %s)"
                cursor.execute(insert_query, (new_certificate_number, "Open"))
                conn.commit()

                container_data = {"CertificateNumber": new_certificate_number, "status": "Open"}

    except Exception as e:
        print(f"Error generating new certificate: {e}")
        container_data = {"CertificateNumber": "Error", "status": "Error"}

    # Pass the data to the template instead of returning JSON
    return render_template('container.html', container_data=container_data)

#####################################################################
#                <--- Admin Container Form --->                     #
#####################################################################



@app.route('/add_survey', methods=['POST'])
@login_required
def add_survey():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Extract form data
                CertificateNumber = request.form.get('CertificateNumber', '').strip()
                date = request.form.get('date', '').strip()
                applicant_for_survey = request.form.get('applicant_for_survey', '').strip()
                date_of_inspection = request.form.get('date_of_inspection', '').strip()
                container_no = request.form.get('container_no', '').strip()
                place_of_inspection = request.form.get('place_of_inspection', '').strip()
                container_type = request.form.get('type', '').strip()
                size = request.form.get('size', '').strip()
                tare_weight = request.form.get('tare_weight', '').strip()
                csc_no = request.form.get('csc_no', '').strip()
                payload_capacity = request.form.get('payload_capacity', '').strip()
                year_of_manufacture = request.form.get('year_of_manufacture', '').strip()
                max_gross_weight = request.form.get('max_gross_weight', '').strip()
                remarks = request.form.get('remarks', '').strip()
                surveyor = request.form.get('surveyor', '').strip()
                action = request.form.get('action')

                # Handle photo uploads
                photo_paths = []
                for i in range(1, 8):
                    photo = request.files.get(f'photo_{i}')
                    if photo and photo.filename != '':
                        filename = secure_filename(f"{CertificateNumber}_photo_{i}.jpg")
                        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

                        print(f"Saving photo {i} to: {photo_path}")  # Debugging statement

                        photo.save(photo_path)
                        photo_paths.append(f"uploads/{filename}")  # Store relative path for easier access
                    else:
                        photo_paths.append(None)



                # Determine status
                status = "Draft" if action == "Save as Draft" else "In Progress"

                # Validate required fields for submission
                if status != "Draft":
                    required_fields = [CertificateNumber, date, applicant_for_survey, date_of_inspection, container_no, place_of_inspection, surveyor]
                    if not all(required_fields):
                        flash("All required fields must be filled!", "error")
                        return redirect(url_for('container'))

                # Check if CertificateNumber exists
                cursor.execute("SELECT COUNT(*) AS count FROM container WHERE CertificateNumber = %s", (CertificateNumber,))
                result = cursor.fetchone()
                if not result or result["count"] == 0:
                    flash(f"Error: Certificate Number {CertificateNumber} not found!", "error")
                    return redirect(url_for('forms'))

                # Update survey record
                update_query = """
                    UPDATE container
                    SET 
                        date = %s, applicant_for_survey = %s, date_of_inspection = %s, container_no = %s,
                        place_of_inspection = %s, type = %s, size = %s, tare_weight = %s, csc_no = %s,
                        payload_capacity = %s, year_of_manufacture = %s, max_gross_weight = %s, 
                        remarks = %s, surveyor = %s, status = %s,
                        photo_1 = %s, photo_2 = %s, photo_3 = %s, photo_4 = %s, photo_5 = %s, photo_6 = %s, photo_7 = %s
                    WHERE CertificateNumber = %s
                """
                values = (
                    date, applicant_for_survey, date_of_inspection, container_no,
                    place_of_inspection, container_type, size, tare_weight, csc_no,
                    payload_capacity, year_of_manufacture, max_gross_weight,
                    remarks, surveyor, status, *photo_paths, CertificateNumber
                )
                cursor.execute(update_query, values)
                conn.commit()
                print("Photo Paths:", photo_paths)

                flash('Survey saved as draft!' if status == "Draft" else 'Survey submitted successfully!', 'success')

                if action == "Submit and New":
                    return redirect(url_for('container'))
                return redirect(url_for('forms'))

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in add_survey: {e}")
        flash(f'An error occurred: {e}', 'error')
        return redirect(url_for('container'))


    
#####################################################################
#                <--- Admin Container Edit --->                     #
#####################################################################

@app.route('/containeredit')
@login_required
def containeredit():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Fetch all container records for editing
        cursor.execute("""
            SELECT CertificateNumber, date, applicant_for_survey, date_of_inspection, container_no, status 
            FROM container
        """)
        container_data = cursor.fetchall()

        conn.close()

        return render_template('containeredit.html', container_data=container_data)
    
    except Exception as e:
        print(f"Error fetching container records for editing: {e}")
        flash("An error occurred while fetching the container records.", "error")
        return redirect(url_for("containeredit"))
     
@app.route('/containeredit1/<int:CertificateNumber>')
@login_required
def containeredit1(CertificateNumber):
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                
                # Fetch container details
                cursor.execute("SELECT * FROM container WHERE CertificateNumber = %s", (CertificateNumber,))
                container_details = cursor.fetchone()

                if not container_details:
                    flash("No record found for the given Certificate Number.", "error")
                    return redirect(url_for("container"))

                # ✅ Debugging: Check if data is retrieved correctly
                print("Container Details:", container_details)

                # Handle survey checkboxes
                survey_data = {}
                survey_checkboxes = container_details.get('survey_checkboxes', '')

                if survey_checkboxes:
                    try:
                        survey_data = json.loads(survey_checkboxes)
                    except json.JSONDecodeError:
                        survey_data = {}  # Default to empty dict
                        flash("Error processing survey checkboxes.", "error")

                return render_template('containeredit1.html', container=container_details, survey_data=survey_data)

    except Exception as e:
        print(f"Error fetching container details: {e}")
        flash("An error occurred while fetching container details.", "error")
        return redirect(url_for("container"))   

#####################################################################
#                <--- Admin Container Edit --->                     #
#####################################################################

@app.route('/update_surveyad/<int:CertificateNumber>', methods=['POST'])
@login_required
def update_surveyad(CertificateNumber):
    print(f"Received update request for CertificateNumber: {CertificateNumber}")  # Debugging line
    print(request.form)
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                
                # Extract form data
                date = request.form.get('date', '').strip()
                applicant_for_survey = request.form.get('applicant_for_survey', '').strip()
                date_of_inspection = request.form.get('date_of_inspection', '').strip()
                container_no = request.form.get('container_no', '').strip()
                place_of_inspection = request.form.get('place_of_inspection', '').strip()
                container_type = request.form.get('type', '').strip()
                size = request.form.get('size', '').strip()
                tare_weight = request.form.get('tare_weight', '').strip()
                csc_no = request.form.get('csc_no', '').strip()
                payload_capacity = request.form.get('payload_capacity', '').strip()
                year_of_manufacture = request.form.get('year_of_manufacture', '').strip()
                max_gross_weight = request.form.get('max_gross_weight', '').strip()
                remarks = request.form.get('remarks', '').strip()
                surveyor = request.form.get('surveyor', '').strip()

                # Validate required fields
                required_fields = {
                    "date": date,
                    "applicant_for_survey": applicant_for_survey,
                    "date_of_inspection": date_of_inspection,
                    "container_no": container_no,
                    "place_of_inspection": place_of_inspection,
                    "surveyor": surveyor,
                }

                for field, value in required_fields.items():
                    if not value:
                        flash(f"Error: {field.replace('_', ' ').title()} is required!", "error")
                        return redirect(url_for('containeredit1', CertificateNumber=CertificateNumber))

                # ✅ Update existing survey record
                update_query = """
                    UPDATE container
                    SET 
                        date = %s, applicant_for_survey = %s, date_of_inspection = %s, container_no = %s,
                        place_of_inspection = %s, type = %s, size = %s, tare_weight = %s, csc_no = %s,
                        payload_capacity = %s, year_of_manufacture = %s, max_gross_weight = %s, 
                        remarks = %s, surveyor = %s, status = 'In Progress'
                    WHERE CertificateNumber = %s
                """
                values = (
                    date, applicant_for_survey, date_of_inspection, container_no, place_of_inspection,
                    container_type, size, tare_weight, csc_no, payload_capacity, year_of_manufacture,
                    max_gross_weight, remarks, surveyor, CertificateNumber
                )

                cursor.execute(update_query, values)
                conn.commit()
                print(f"Received data: {request.form.to_dict()}")

                flash('Survey updated successfully!', 'success')
                return redirect(url_for('admindash'))  # Redirect to container list

    except Exception as e:
        print(f"Error: {e}")
        flash(f'An error occurred: {e}', 'error')
        return redirect(url_for('admindash'))
#####################################################################
#                <--- Admin Container Report --->                   #
#####################################################################
@app.route('/reportContainer')
@login_required
def reportContainer():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Fetch all container records
        cursor.execute("SELECT CertificateNumber, date, applicant_for_survey, date_of_inspection, container_no ,status FROM container")
        container_data = cursor.fetchall()

        conn.close()

        return render_template('reportContainer.html', container_data=container_data)
    except Exception as e:
        print(f"Error: {e}")
        flash('An error occurred while fetching the container records.', 'error')
        return redirect(url_for('reportContainer'))

#####################################################################
#         <--- Admin Container Report Delete (Id) --->              #
#####################################################################
@app.route('/delete_container/<int:certificate_number>', methods=['POST'])
@login_required
def delete_container(certificate_number):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete the record from the 'container' table
        cursor.execute("DELETE FROM container WHERE CertificateNumber = %s", (certificate_number,))
        conn.commit()

        conn.close()
        flash('Container record deleted successfully.', 'success')
    except Exception as e:
        print(f"Error: {e}")
        flash('An error occurred while deleting the container record.', 'error')

    return redirect(url_for('reportContainer'))

#####################################################################
#     <--- Admin Container Report Global Delete --->                #
#####################################################################

@app.route('/delete-certificate', methods=['POST']) 
@login_required
def delete_certificate():
    try:
        data = request.get_json()
        certificate_ids = data.get('ids', [])

        if not certificate_ids:
            return jsonify({"error": "No certificate IDs provided"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure there are IDs to delete
        if certificate_ids:
            format_strings = ','.join(['%s'] * len(certificate_ids))
            query = f"DELETE FROM container WHERE CertificateNumber IN ({format_strings})"
            cursor.execute(query, tuple(certificate_ids))
            conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"message": "Certificates deleted successfully"}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": "An error occurred while deleting certificates"}), 500

#####################################################################
#            <--- Admin Container Report (ID)--->                   #
#####################################################################

@app.route('/reportContainer1/<int:CertificateNumber>')
@login_required
def reportContainer1(CertificateNumber):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Fetch the container details based on CertificateNumber
        cursor.execute("""
            SELECT * FROM container WHERE CertificateNumber = %s
        """, (CertificateNumber,))
        container_details = cursor.fetchone()

        # Debug: print the fetched data
        print(container_details)  # This will print all fields of container_details

        conn.close()

        if not container_details:
            flash("No record found for the given Certificate Number.", "error")
            return redirect(url_for("reportContainer"))

        # Optionally handle any survey data or survey checkboxes if needed
        survey_data = {}
        if container_details.get('survey_checkboxes'):
            try:
                survey_data = json.loads(container_details['survey_checkboxes'])
            except json.JSONDecodeError:
                flash("Error processing survey checkboxes.", "error")

        return render_template('reportContainer1.html', container=container_details, survey_data=survey_data)

    except Exception as e:
        print(f"Error fetching container report: {e}")
        flash("An error occurred while fetching the container report.", "error")
        return redirect(url_for("reportContainer"))
    
#####################################################################
#                 <--- Admin Container--->                          #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
#########################END#########################################

#####################################################################
#              <--- Employee Container--->                          #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
########################START########################################

@app.route('/add_surveyem,', methods=['POST'])
@login_required
def add_surveyem():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Extract form data
                CertificateNumber = request.form.get('CertificateNumber', '').strip()
                date = request.form.get('date', '').strip()
                applicant_for_survey = request.form.get('applicant_for_survey', '').strip()
                date_of_inspection = request.form.get('date_of_inspection', '').strip()
                container_no = request.form.get('container_no', '').strip()
                place_of_inspection = request.form.get('place_of_inspection', '').strip()
                container_type = request.form.get('type', '').strip()
                size = request.form.get('size', '').strip()
                tare_weight = request.form.get('tare_weight', '').strip()
                csc_no = request.form.get('csc_no', '').strip()
                payload_capacity = request.form.get('payload_capacity', '').strip()
                year_of_manufacture = request.form.get('year_of_manufacture', '').strip()
                max_gross_weight = request.form.get('max_gross_weight', '').strip()
                remarks = request.form.get('remarks', '').strip()
                surveyor = request.form.get('surveyor', '').strip()
                action = request.form.get('action')

                # Handle photo uploads
                photo_paths = []
                for i in range(1, 8):
                    photo = request.files.get(f'photo_{i}')
                    if photo and photo.filename != '':
                        filename = secure_filename(f"{CertificateNumber}_photo_{i}.jpg")
                        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

                        print(f"Saving photo {i} to: {photo_path}")  # Debugging statement

                        photo.save(photo_path)
                        photo_paths.append(f"uploads/{filename}")  # Store relative path for easier access
                    else:
                        photo_paths.append(None)



                # Determine status
                status = "Draft" if action == "Save as Draft" else "In Progress"

                # Validate required fields for submission
                if status != "Draft":
                    required_fields = [CertificateNumber, date, applicant_for_survey, date_of_inspection, container_no, place_of_inspection, surveyor]
                    if not all(required_fields):
                        flash("All required fields must be filled!", "error")
                        return redirect(url_for('container'))

                # Check if CertificateNumber exists
                cursor.execute("SELECT COUNT(*) AS count FROM container WHERE CertificateNumber = %s", (CertificateNumber,))
                result = cursor.fetchone()
                if not result or result["count"] == 0:
                    flash(f"Error: Certificate Number {CertificateNumber} not found!", "error")
                    return redirect(url_for('forms'))

                # Update survey record
                update_query = """
                    UPDATE container
                    SET 
                        date = %s, applicant_for_survey = %s, date_of_inspection = %s, container_no = %s,
                        place_of_inspection = %s, type = %s, size = %s, tare_weight = %s, csc_no = %s,
                        payload_capacity = %s, year_of_manufacture = %s, max_gross_weight = %s, 
                        remarks = %s, surveyor = %s, status = %s,
                        photo_1 = %s, photo_2 = %s, photo_3 = %s, photo_4 = %s, photo_5 = %s, photo_6 = %s, photo_7 = %s
                    WHERE CertificateNumber = %s
                """
                values = (
                    date, applicant_for_survey, date_of_inspection, container_no,
                    place_of_inspection, container_type, size, tare_weight, csc_no,
                    payload_capacity, year_of_manufacture, max_gross_weight,
                    remarks, surveyor, status, *photo_paths, CertificateNumber
                )
                cursor.execute(update_query, values)
                conn.commit()
                print("Photo Paths:", photo_paths)

                flash('Survey saved as draft!' if status == "Draft" else 'Survey submitted successfully!', 'success')

                # ✅ Redirect based on action
                if action == "Submit and New":
                    return redirect(url_for('empcontainer'))  # Redirect to form for new entry
                return redirect(url_for('empforms'))  # Default redirect to forms page

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in add_survey: {e}")

        flash(f'An error occurred: {e}', 'error')
        return redirect(url_for('empcontainer')) 
    
@app.route('/empcontainer')
@login_required
def empcontainer():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                conn.begin()

                # Get the last certificate number
                cursor.execute("SELECT CertificateNumber FROM container ORDER BY id DESC LIMIT 1 FOR UPDATE")
                last_record = cursor.fetchone()

                if last_record and last_record["CertificateNumber"].isdigit():
                    next_number = int(last_record["CertificateNumber"]) + 1
                else:
                    next_number = 1  # Start from 1 if no records exist

                new_certificate_number = str(next_number)

                # Insert new certificate
                insert_query = "INSERT INTO container (CertificateNumber, status) VALUES (%s, %s)"
                cursor.execute(insert_query, (new_certificate_number, "Open"))
                conn.commit()

                container_data = {"CertificateNumber": new_certificate_number, "status": "Open"}

    except Exception as e:
        print(f"Error generating new certificate: {e}")
        container_data = {"CertificateNumber": "Error", "status": "Error"}

    # Pass the data to the template instead of returning JSON
    return render_template('empcontainer.html', container_data=container_data)


    
@app.route('/empcontaineredit')
@login_required
def empcontaineredit():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Fetch all container records for editing
        cursor.execute("""
            SELECT CertificateNumber, date, applicant_for_survey, date_of_inspection, container_no, status 
            FROM container
        """)
        container_data = cursor.fetchall()

        conn.close()

        return render_template('empcontaineredit.html', container_data=container_data)
    
    except Exception as e:
        print(f"Error fetching container records for editing: {e}")
        flash("An error occurred while fetching the container records.", "error")
        return redirect(url_for("empcontaineredit")) 

@app.route('/empcontaineredit1/<int:CertificateNumber>')
@login_required
def empcontaineredit1(CertificateNumber):
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                
                # Fetch container details
                cursor.execute("SELECT * FROM container WHERE CertificateNumber = %s", (CertificateNumber,))
                container_details = cursor.fetchone()

                if not container_details:
                    flash("No record found for the given Certificate Number.", "error")
                    return redirect(url_for("empcontainer"))

                # ✅ Debugging: Check if data is retrieved correctly
                print("Container Details:", container_details)

                # Handle survey checkboxes
                survey_data = {}
                survey_checkboxes = container_details.get('survey_checkboxes', '')

                if survey_checkboxes:
                    try:
                        survey_data = json.loads(survey_checkboxes)
                    except json.JSONDecodeError:
                        survey_data = {}  # Default to empty dict
                        flash("Error processing survey checkboxes.", "error")

                return render_template('empcontaineredit1.html', container=container_details, survey_data=survey_data)

    except Exception as e:
        print(f"Error fetching container details: {e}")
        flash("An error occurred while fetching container details.", "error")
        return redirect(url_for("empcontainer"))

@app.route('/update_survey/<int:CertificateNumber>', methods=['POST'])
@login_required
def update_survey(CertificateNumber):
    print(f"Received update request for CertificateNumber: {CertificateNumber}")  # Debugging line
    print(request.form)
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                
                # Extract form data
                date = request.form.get('date', '').strip()
                applicant_for_survey = request.form.get('applicant_for_survey', '').strip()
                date_of_inspection = request.form.get('date_of_inspection', '').strip()
                container_no = request.form.get('container_no', '').strip()
                place_of_inspection = request.form.get('place_of_inspection', '').strip()
                container_type = request.form.get('type', '').strip()
                size = request.form.get('size', '').strip()
                tare_weight = request.form.get('tare_weight', '').strip()
                csc_no = request.form.get('csc_no', '').strip()
                payload_capacity = request.form.get('payload_capacity', '').strip()
                year_of_manufacture = request.form.get('year_of_manufacture', '').strip()
                max_gross_weight = request.form.get('max_gross_weight', '').strip()
                remarks = request.form.get('remarks', '').strip()
                surveyor = request.form.get('surveyor', '').strip()

                # Validate required fields
                required_fields = {
                    "date": date,
                    "applicant_for_survey": applicant_for_survey,
                    "date_of_inspection": date_of_inspection,
                    "container_no": container_no,
                    "place_of_inspection": place_of_inspection,
                    "surveyor": surveyor,
                }

                for field, value in required_fields.items():
                    if not value:
                        flash(f"Error: {field.replace('_', ' ').title()} is required!", "error")
                        return redirect(url_for('empcontaineredit1', CertificateNumber=CertificateNumber))

                # ✅ Update existing survey record
                update_query = """
                    UPDATE container
                    SET 
                        date = %s, applicant_for_survey = %s, date_of_inspection = %s, container_no = %s,
                        place_of_inspection = %s, type = %s, size = %s, tare_weight = %s, csc_no = %s,
                        payload_capacity = %s, year_of_manufacture = %s, max_gross_weight = %s, 
                        remarks = %s, surveyor = %s, status = 'In Progress'
                    WHERE CertificateNumber = %s
                """
                values = (
                    date, applicant_for_survey, date_of_inspection, container_no, place_of_inspection,
                    container_type, size, tare_weight, csc_no, payload_capacity, year_of_manufacture,
                    max_gross_weight, remarks, surveyor, CertificateNumber
                )

                cursor.execute(update_query, values)
                conn.commit()
                print(f"Received data: {request.form.to_dict()}")

                flash('Survey updated successfully!', 'success')
                return redirect(url_for('empdash'))  # Redirect to container list

    except Exception as e:
        print(f"Error: {e}")
        flash(f'An error occurred: {e}', 'error')
        return redirect(url_for('empadsh'))

#####################################################################
#              <--- Employee Container--->                          #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
##########################END########################################




@app.route('/employee')
@login_required
def employee():
    return render_template('employee.html')


@app.route('/forms')
@login_required
def forms():
    return render_template('forms.html')

@app.route('/formson')
@login_required
def formson():
    return render_template('formson.html')

@app.route('/formsnew')
@login_required
def formsnew():
    return render_template('formsnew.html')

@app.route('/certificatert')
@login_required
def certificatert():
    return render_template('certificatert.html')

@app.route('/certificaterpt')
@login_required
def certificaterpt():
    return render_template('certificaterpt.html')

@app.route('/containerrpt')
@login_required
def containerrpt():
    return render_template('containerrpt.html')
#####################################################################
#                       <--- Admin FCL--->                          #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
##########################START######################################

@app.route('/emp')
@login_required
def emp():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                conn.begin()

                # 🔹 Fetch the latest CertificateNumber and status
                cursor.execute("SELECT CertificateNumber FROM form ORDER BY id DESC LIMIT 1 FOR UPDATE")
                last_record = cursor.fetchone()

                if last_record and last_record["CertificateNumber"].isdigit():
                    next_number = int(last_record["CertificateNumber"]) + 1
                else:
                    next_number = 1  # Start from 1 if no records exist

                # 🔹 Generate new Certificate Number
                new_certificate_number = str(next_number)

                # Insert new certificate with status "Open"
                cursor.execute("INSERT INTO form (CertificateNumber, status) VALUES (%s, %s)", 
                               (new_certificate_number, "Open"))
                conn.commit()

                # Prepare data for template
                form_data = {"CertificateNumber": new_certificate_number, "status": "Open"}

    except Exception as e:
        conn.rollback()  # Rollback if there's an error
        print(f"Error generating form data: {e}")
        form_data = {"CertificateNumber": "Error", "status": "Error"}

    print("Fetched Form Data:", form_data)  # ✅ Debugging log

    return render_template('emp.html', form=form_data)


@app.route('/get_latest_')
@login_required
def get_latest_():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute("SELECT CertificateNumber, status FROM form ORDER BY id DESC LIMIT 1")
                certificate_data = cursor.fetchone()

        if not certificate_data:
            certificate_data = {"CertificateNumber": "N/A", "status": "Unknown"}

    except Exception as e:
        print(f"Error fetching latest certificate: {e}")
        certificate_data = {"CertificateNumber": "Error", "status": "Error"}

    return jsonify(certificate_data)


@app.route('/get_consignment_details')
@login_required
def get_consignment_details():
    conn = None  # Initialize connection variable
    try:
        conn = pymysql.connect(
            host="localhost",
            user="root",
            password="Money2035",
            database="leads"
        )
        cursor = conn.cursor()

        # ✅ Only fetch consignments where status is 'In Progress'
        cursor.execute("""
            SELECT id, shipper, consignee, commodity, sb_number, total_pkgs, gross_weight, total_volume, status
            FROM cer
            WHERE status = 'In Progress'
        """)

        consignments = cursor.fetchall()
        
        consignment_data = [
            {
                "id": row[0],  
                "shipper": row[1],
                "consignee": row[2],
                "commodity": row[3],
                "sb_number": row[4],
                "total_pkgs": row[5],
                "gross_weight": row[6],
                "total_volume": row[7],
                "status": row[8]
            }
            for row in consignments
        ]

        print("Filtered Consignment Data:", consignment_data)  # ✅ Debugging
        return jsonify(consignment_data)

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": "Unable to fetch consignment details"}), 500

    finally:
        if conn:
            conn.close()  # ✅ Ensure connection closes




@app.route('/get_containers')
@login_required
def get_containers():
    try:
        conn = pymysql.connect(
            host="localhost",
            user="root",
            password="Money2035",
            database="leads"
        )
        cursor = conn.cursor()

        # ✅ Only fetch containers where status is 'In Progress'
        cursor.execute("""
            SELECT container_no, applicant_for_survey, size, tare_weight, 
                   payload_capacity, max_gross_weight, status 
            FROM container
            WHERE status = 'In Progress'
        """)

        containers = cursor.fetchall()
        conn.close()

        container_data = []
        for row in containers:
            container_data.append({
                "container_no": row[0],
                "applicant_for_survey": row[1],
                "size": row[2],
                "tare_weight": row[3],
                "payload_capacity": row[4],
                "max_gross_weight": row[5],
                "status": row[6]
            })

        print("Filtered Container Data:", container_data)  # ✅ Debugging
        return jsonify(container_data)

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": "Unable to fetch container details"}), 500




#FCL FORM in app.py 
@app.route('/submit', methods=['POST'])
@login_required
def submit():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get form data
        CertificateNumber = request.form.get('CertificateNumber', '').strip()
        date = request.form.get('date', '').strip()
        applicant_name = request.form.get('applicantName', '').strip()
        container_number = request.form.get('containerNumber', '').strip()
        size_type = request.form.get('sizeType', '').strip()
        tare_weight = request.form.get('tareWeight', '').strip()
        payload_capacity = request.form.get('payloadCapacity', '').strip()
        declared_total_weight = request.form.get('declaredTotalWeight', '').strip()
        stuffing_comm_date_time = request.form.get('stuffingCommDateTime', '').strip()
        stuffing_comp_date_time = request.form.get('stuffingCompDateTime', '').strip()
        seal_number = request.form.get('sealNumber', '').strip()
        seal_date_time = request.form.get('sealDateTime', '').strip()
        port_of_discharge = request.form.get('portOfDischarge', '').strip()
        place_of_stuffing = request.form.get('placeOfStuffing', '').strip()
        cbm = request.form.get('volume', '').strip()
        loading_condition = request.form.get('loadingCondition', '').strip()
        lashing = request.form.get('lashing', '').strip()
        others = request.form.get('others', '').strip()
        weather_condition = request.form.get('weatherCondition', '').strip()
        surveyor_name = request.form.get('surveyorName', '').strip()
        signature = request.form.get('signature', '').strip()
        totalPackages = request.form.get('totalPackages', '').strip()
        gross_weight = request.form.get('grossWeight', '').strip()
        total_container_weight = request.form.get('TotalContainerWeight', '').strip()


        # Get button action
        action = request.form.get('action', '')

        # ✅ Determine status based on action
        status = "Draft" if action == "Save as Draft" else "Completed"

        # ✅ Validate required fields only for "Submit"
        if status == "Completed":
            required_fields = {
                "Certificate Number": CertificateNumber,
                "Date": date,
                "Applicant Name": applicant_name,
                "Container Number": container_number,
                "Surveyor Name": surveyor_name
            }

            for field, value in required_fields.items():
                if not value:
                    flash(f"Error: {field} is required!", "error")
                    return redirect(url_for("forms"))

        # ✅ Parse and validate consignment details safely
        consignment_details = request.form.get('consignmentDetails', '[]').strip()
        try:
            consignment_details = json.loads(consignment_details)
            if not isinstance(consignment_details, list):
                consignment_details = []  # Ensure it's always a list
        except json.JSONDecodeError:
            consignment_details = []  # Default to empty list if invalid

        # ✅ Check if Certificate Number exists before updating
        cursor.execute("SELECT 1 FROM form WHERE CertificateNumber = %s", (CertificateNumber,))
        if not cursor.fetchone():
            flash("Error: Certificate Number not found in the database.", "error")
            return redirect(url_for("forms"))

        # ✅ Update the form entry
        update_form_query = """
            UPDATE form
            SET date = %s, applicant_name = %s, container_number = %s, size_type = %s, tare_weight = %s, 
                payload_capacity = %s, declared_total_weight = %s, stuffing_comm_date_time = %s, 
                stuffing_comp_date_time = %s, seal_number = %s, seal_date_time = %s, port_of_discharge = %s, 
                place_of_stuffing = %s, cbm = %s, total_gross_weight = %s, total_container_weight = %s, 
                loading_condition = %s, lashing = %s, others = %s, weather_condition = %s, surveyor_name = %s, 
                signature = %s, totalPackages = %s, consignment_details = %s, status = %s
            WHERE CertificateNumber = %s
        """

        cursor.execute(update_form_query, (
            date or None, applicant_name or None, container_number or None, size_type or None,
            tare_weight or None, payload_capacity or None, declared_total_weight or None,
            stuffing_comm_date_time or None, stuffing_comp_date_time or None, seal_number or None, seal_date_time or None,
            port_of_discharge or None, place_of_stuffing or None, cbm or None, gross_weight or None,
            total_container_weight or None, loading_condition or None, lashing or None, others or None, weather_condition or None,
            surveyor_name or None, signature or None, totalPackages or None, json.dumps(consignment_details),
            status, CertificateNumber
        ))


        # ✅ If submitting, update container and consignment status
        if status == "Completed":
            cursor.execute(
                "UPDATE container SET status = 'Completed' WHERE container_no = %s AND status = 'In Progress'",
                (container_number,)
            )

            # ✅ Update related consignments
            consignment_ids = [item["id"] for item in consignment_details if "id" in item]
            if consignment_ids:
                format_strings = ",".join(["%s"] * len(consignment_ids))
                cursor.execute(
                    f"UPDATE cer SET status = 'Completed' WHERE id IN ({format_strings})",
                    tuple(consignment_ids)
                )

        # ✅ Commit changes
        conn.commit()

        flash("Form saved as draft!" if status == "Draft" else "Form submitted successfully!", "success")

        # ✅ Redirect based on action
        return redirect(url_for('emp')) if action == "Submit and New" else redirect(url_for("forms"))

    except Exception as e:
        print(f"Error: {e}")
        flash(f'An error occurred while processing the form. Error: {e}', 'error')
        return redirect(url_for('forms'))
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()





@app.route('/empedit')
@login_required
def empedit():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Fetch employee records for editing
                cursor.execute("""
                    SELECT CertificateNumber, date, applicant_name, container_number, status 
                    FROM form
                """
                )
                form_data = cursor.fetchall()

        return render_template('empedit.html', form=form_data)
    
    except Exception as e:
        print(f"Error fetching employee records for editing: {e}")
        flash('An error occurred while fetching the employee records.', 'error')
        return redirect(url_for('admindash'))

@app.route('/empedit1/<int:CertificateNumber>')
@login_required
def empedit1(CertificateNumber):
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                print(f"Fetching CertificateNumber: {CertificateNumber}")  # Debug Print

                cursor.execute("SELECT * FROM form WHERE CertificateNumber = %s", (CertificateNumber,))
                form_details = cursor.fetchone()

                if not form_details:
                    flash("No record found for the given Certificate Number.", "error")
                    return redirect(url_for("empedit"))  # ✅ Redirect if no record found

                print("Form Details:", form_details)  # Debug Print

                return render_template('empedit1.html', form=form_details)

    except Exception as e:
        print(f"Error fetching form details: {e}")
        flash("An error occurred while fetching form details.", "error")
        return redirect(url_for("empedit"))  # ✅ Redirect in case of error

def safe_float(value):
    try:
        return float(value.strip()) if value and value.strip() else None
    except ValueError:
        return None

@app.route('/update_formad/<int:CertificateNumber>', methods=['POST'])
@login_required
def update_formad(CertificateNumber):
    print(f"Received update request for CertificateNumber: {CertificateNumber}")  # Debugging
    print(request.form.to_dict())  # Debugging

    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                
                # Extract form data
                form_data = {
                    "date": request.form.get("date", "").strip() or None,
                    "applicant_name": request.form.get("applicantName", "").strip() or None,
                    "container_number": request.form.get("containerNumber", "").strip() or None,
                    "size_type": request.form.get("sizeType", "").strip() or None,
                    "tare_weight": request.form.get("tareWeight", "").strip() or None,
                    "payload_capacity": request.form.get("payloadCapacity", "").strip() or None,
                    "declared_total_weight": request.form.get("declaredTotalWeight", "").strip() or None,
                    "stuffing_comm_date_time": request.form.get("stuffingCommDateTime", "").strip() or None,
                    "stuffing_comp_date_time": request.form.get("stuffingCompDateTime", "").strip() or None,
                    "seal_number": request.form.get("sealNumber", "").strip() or None,
                    "port_of_discharge": request.form.get("portOfDischarge", "").strip() or None,
                    "place_of_stuffing": request.form.get("placeOfStuffing", "").strip() or None,
                    "cbm": safe_float(request.form.get("volume", "")),  
                    "loading_condition": request.form.get("loadingCondition", "").strip() or None,
                    "lashing": request.form.get("lashing", "").strip() or None,
                    "others": request.form.get("others", "").strip() or None,
                    "weather_condition": request.form.get("weatherCondition", "").strip() or None,
                    "surveyor_name": request.form.get("surveyorName", "").strip() or None,
                    "signature": request.form.get("signature", "").strip() or None,
                    "totalPackages": safe_float(request.form.get("totalPackages", "")),
                    "gross_weight": safe_float(request.form.get("grossWeight", ""))
                }

                # ✅ Get the action (Save as Draft or Submit)
                action = request.form.get("action")
                status = "Draft" if action == "Save as Draft" else "Completed"

                # ✅ Validate required fields only if submitting
                if status == "Completed":
                    required_fields = {
                        "date": form_data["date"],
                        "applicant_name": form_data["applicant_name"],
                        "container_number": form_data["container_number"],
                        "surveyor_name": form_data["surveyor_name"]
                    }
                    for field, value in required_fields.items():
                        if not value:
                            flash(f"Error: {field.replace('_', ' ').title()} is required!", "error")
                            return redirect(url_for("empedit1", CertificateNumber=CertificateNumber))

                # ✅ Retrieve and validate consignment details
                consignment_details = request.form.get("consignmentDetails", "[]").strip()
                try:
                    consignment_details = json.loads(consignment_details)
                    if not isinstance(consignment_details, list):
                        consignment_details = []  # Ensure it's always a list
                except json.JSONDecodeError:
                    consignment_details = []  # Default to empty list if invalid

                # ✅ Update form entry
                update_form_query = """
                    UPDATE form
                    SET date = %s, applicant_name = %s, container_number = %s, size_type = %s, tare_weight = %s, 
                        payload_capacity = %s, declared_total_weight = %s, stuffing_comm_date_time = %s, 
                        stuffing_comp_date_time = %s, seal_number = %s, port_of_discharge = %s, place_of_stuffing = %s, 
                        cbm = %s, loading_condition = %s, lashing = %s, others = %s, 
                        weather_condition = %s, surveyor_name = %s, signature = %s, totalPackages = %s, 
                        consignment_details = %s, status = %s
                    WHERE CertificateNumber = %s
                """
                values = (
                    form_data["date"], form_data["applicant_name"], form_data["container_number"], 
                    form_data["size_type"], form_data["tare_weight"], form_data["payload_capacity"], 
                    form_data["declared_total_weight"], form_data["stuffing_comm_date_time"], 
                    form_data["stuffing_comp_date_time"], form_data["seal_number"], 
                    form_data["port_of_discharge"], form_data["place_of_stuffing"], form_data["cbm"], 
                    form_data["loading_condition"], form_data["lashing"], form_data["others"], 
                    form_data["weather_condition"], form_data["surveyor_name"], form_data["signature"], 
                    form_data["totalPackages"], json.dumps(consignment_details), status, CertificateNumber
                )
                cursor.execute(update_form_query, values)

                # ✅ If submitting, update container and consignment status
                if status == "Completed":
                    update_container_query = """
                        UPDATE container
                        SET status = 'Completed'
                        WHERE container_no = %s AND status = 'In Progress'
                    """
                    cursor.execute(update_container_query, (form_data["container_number"],))

                    # ✅ Update related consignments only if consignment_details is not empty
                    consignment_ids = [item["id"] for item in consignment_details if "id" in item]
                    if consignment_ids:
                        format_strings = ",".join(["%s"] * len(consignment_ids))
                        update_consignment_query = f"""
                            UPDATE cer
                            SET status = 'Completed'
                            WHERE id IN ({format_strings})
                        """
                        cursor.execute(update_consignment_query, tuple(consignment_ids))

                # ✅ Commit changes
                conn.commit()
                flash(f"Form saved as draft!" if status == "Draft" else f"Form submitted successfully!", "success")
                return redirect(url_for("empdash"))  # Redirect to dashboard

    except Exception as e:
        print(f"Error updating form: {e}")
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for("empedit1", CertificateNumber=CertificateNumber))

#####################################################################
#                   <--- Admin FCL Report--->                       #
##############################START##################################
@app.route('/reportFCL')
@login_required
def reportFCL():
    try:
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Fetch relevant data from the `form` table
        cursor.execute("SELECT CertificateNumber, date, applicant_name, container_number ,status FROM form")
        form = cursor.fetchall()

        conn.close()

        # Pass the data to the report.html template
        return render_template('reportFCL.html', form=form)
    except Error as e:
        print(f"Error: {e}")
        flash('An error occurred while fetching the reports. Please try again.', 'error')
        return redirect(url_for('reportFCL'))

@app.route('/delete_fcl/<int:certificate_number>', methods=['POST'])
@login_required
def delete_fcl(certificate_number):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete the record from the 'form' table
        cursor.execute("DELETE FROM form WHERE CertificateNumber = %s", (certificate_number,))
        conn.commit()

        conn.close()
        flash('FCL report deleted successfully.', 'success')
    except Exception as e:
        print(f"Error: {e}")
        flash('An error occurred while deleting the FCL report.', 'error')

    return redirect(url_for('reportFCL'))

@app.route('/delete-fcl1', methods=['POST'])  # Removed <int:certificate_ids> from URL
@login_required
def delete_fcl1():
    try:
        data = request.get_json()
        certificate_ids = data.get('ids', [])

        if not certificate_ids:
            return jsonify({"error": "No certificate IDs provided"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure there are IDs to delete
        if certificate_ids:
            format_strings = ','.join(['%s'] * len(certificate_ids))
            query = f"DELETE FROM form WHERE CertificateNumber IN ({format_strings})"
            cursor.execute(query, tuple(certificate_ids))
            conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"message": "Certificates deleted successfully"}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": "An error occurred while deleting certificates"}), 500



@app.route('/reportFCL1/<int:CertificateNumber>')
@login_required
def reportFCL1(CertificateNumber):
    conn = None
    cursor = None
    try:
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch the report from the `form` table
        cursor.execute("SELECT * FROM form WHERE CertificateNumber = %s", (CertificateNumber,))
        form = cursor.fetchone()  # Fetch a single row

        # Handle case where no data is found
        if not form:
            flash('No report found for the given Certificate Number.', 'error')
            return redirect(url_for('reportFCL'))

        # Parse the `consignment_details` JSON string into a Python object
        if 'consignment_details' in form and form['consignment_details']:
            try:
                form['consignment_details'] = json.loads(form['consignment_details'])
            except json.JSONDecodeError:
                form['consignment_details'] = []  # Default to an empty list if JSON is invalid
        else:
            form['consignment_details'] = []

        # Render the template with the fetched data
        return render_template('reportFCL1.html', form=form)

    except pymysql.Error as e:
        print(f"Database Error: {e}")
        flash('An error occurred while fetching the reports. Please try again.', 'error')
        return redirect(url_for('reportFCL'))

    finally:
        # Close cursor and connection
        if cursor:
            cursor.close()
        if conn:
            conn.close()


#####################################################################
#                       <--- Admin FCL--->                          #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
##########################END########################################

#####################################################################
#                    <--- Employee FCL--->                          #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
##########################START######################################

@app.route('/empemp')
@login_required
def empemp():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                conn.begin()

                # 🔹 Fetch the latest CertificateNumber and status
                cursor.execute("SELECT CertificateNumber FROM form ORDER BY id DESC LIMIT 1 FOR UPDATE")
                last_record = cursor.fetchone()

                if last_record and last_record["CertificateNumber"].isdigit():
                    next_number = int(last_record["CertificateNumber"]) + 1
                else:
                    next_number = 1  # Start from 1 if no records exist

                # 🔹 Generate new Certificate Number
                new_certificate_number = str(next_number)

                # Insert new certificate with status "Open"
                cursor.execute("INSERT INTO form (CertificateNumber, status) VALUES (%s, %s)", 
                               (new_certificate_number, "Open"))
                conn.commit()

                # Prepare data for template
                form_data = {"CertificateNumber": new_certificate_number, "status": "Open"}

    except Exception as e:
        conn.rollback()  # Rollback if there's an error
        print(f"Error generating form data: {e}")
        form_data = {"CertificateNumber": "Error", "status": "Error"}

    print("Fetched Form Data:", form_data)  # ✅ Debugging log

    return render_template('empemp.html', form=form_data)

@app.route('/submitem', methods=['POST'])
@login_required
def submitem():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get form data
        CertificateNumber = request.form.get('CertificateNumber', '').strip()
        date = request.form.get('date', '').strip()
        applicant_name = request.form.get('applicantName', '').strip()
        container_number = request.form.get('containerNumber', '').strip()
        size_type = request.form.get('sizeType', '').strip()
        tare_weight = request.form.get('tareWeight', '').strip()
        payload_capacity = request.form.get('payloadCapacity', '').strip()
        declared_total_weight = request.form.get('declaredTotalWeight', '').strip()
        stuffing_comm_date_time = request.form.get('stuffingCommDateTime', '').strip()
        stuffing_comp_date_time = request.form.get('stuffingCompDateTime', '').strip()
        seal_number = request.form.get('sealNumber', '').strip()
        seal_date_time = request.form.get('sealDateTime', '').strip()
        port_of_discharge = request.form.get('portOfDischarge', '').strip()
        place_of_stuffing = request.form.get('placeOfStuffing', '').strip()
        cbm = request.form.get('volume', '').strip()
        loading_condition = request.form.get('loadingCondition', '').strip()
        lashing = request.form.get('lashing', '').strip()
        others = request.form.get('others', '').strip()
        weather_condition = request.form.get('weatherCondition', '').strip()
        surveyor_name = request.form.get('surveyorName', '').strip()
        signature = request.form.get('signature', '').strip()
        totalPackages = request.form.get('totalPackages', '').strip()
        gross_weight = request.form.get('grossWeight', '').strip()
        total_container_weight = request.form.get('TotalContainerWeight', '').strip()


        # Get button action
        action = request.form.get('action', '')

        # ✅ Determine status based on action
        status = "Draft" if action == "Save as Draft" else "Completed"

        # ✅ Validate required fields only for "Submit"
        if status == "Completed":
            required_fields = {
                "Certificate Number": CertificateNumber,
                "Date": date,
                "Applicant Name": applicant_name,
                "Container Number": container_number,
                "Surveyor Name": surveyor_name
            }

            for field, value in required_fields.items():
                if not value:
                    flash(f"Error: {field} is required!", "error")
                    return redirect(url_for("forms"))

        # ✅ Parse and validate consignment details safely
        consignment_details = request.form.get('consignmentDetails', '[]').strip()
        try:
            consignment_details = json.loads(consignment_details)
            if not isinstance(consignment_details, list):
                consignment_details = []  # Ensure it's always a list
        except json.JSONDecodeError:
            consignment_details = []  # Default to empty list if invalid

        # ✅ Check if Certificate Number exists before updating
        cursor.execute("SELECT 1 FROM form WHERE CertificateNumber = %s", (CertificateNumber,))
        if not cursor.fetchone():
            flash("Error: Certificate Number not found in the database.", "error")
            return redirect(url_for("forms"))

        # ✅ Update the form entry
        update_form_query = """
            UPDATE form
            SET date = %s, applicant_name = %s, container_number = %s, size_type = %s, tare_weight = %s, 
                payload_capacity = %s, declared_total_weight = %s, stuffing_comm_date_time = %s, 
                stuffing_comp_date_time = %s, seal_number = %s, seal_date_time = %s, port_of_discharge = %s, 
                place_of_stuffing = %s, cbm = %s, total_gross_weight = %s, total_container_weight = %s, 
                loading_condition = %s, lashing = %s, others = %s, weather_condition = %s, surveyor_name = %s, 
                signature = %s, totalPackages = %s, consignment_details = %s, status = %s
            WHERE CertificateNumber = %s
        """

        cursor.execute(update_form_query, (
            date or None, applicant_name or None, container_number or None, size_type or None,
            tare_weight or None, payload_capacity or None, declared_total_weight or None,
            stuffing_comm_date_time or None, stuffing_comp_date_time or None, seal_number or None, seal_date_time or None,
            port_of_discharge or None, place_of_stuffing or None, cbm or None, gross_weight or None,
            total_container_weight or None, loading_condition or None, lashing or None, others or None, weather_condition or None,
            surveyor_name or None, signature or None, totalPackages or None, json.dumps(consignment_details),
            status, CertificateNumber
        ))


        # ✅ If submitting, update container and consignment status
        if status == "Completed":
            cursor.execute(
                "UPDATE container SET status = 'Completed' WHERE container_no = %s AND status = 'In Progress'",
                (container_number,)
            )

            # ✅ Update related consignments
            consignment_ids = [item["id"] for item in consignment_details if "id" in item]
            if consignment_ids:
                format_strings = ",".join(["%s"] * len(consignment_ids))
                cursor.execute(
                    f"UPDATE cer SET status = 'Completed' WHERE id IN ({format_strings})",
                    tuple(consignment_ids)
                )

        # ✅ Commit changes
        conn.commit()

        flash("Form saved as draft!" if status == "Draft" else "Form submitted successfully!", "success")

        # ✅ Redirect based on action
        return redirect(url_for('empemp')) if action == "Submit and New" else redirect(url_for("empforms"))

    except Exception as e:
        print(f"Error: {e}")
        flash(f'An error occurred while processing the form. Error: {e}', 'error')
        return redirect(url_for('empforms'))
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/empempedit')
@login_required
def empempedit():
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # Fetch employee records for editing
                cursor.execute("""
                    SELECT CertificateNumber, date, applicant_name, container_number, status 
                    FROM form
                """
                )
                form_data = cursor.fetchall()

        return render_template('empempedit.html', form=form_data)
    
    except Exception as e:
        print(f"Error fetching employee records for editing: {e}")
        flash('An error occurred while fetching the employee records.', 'error')
        return redirect(url_for('empdash'))


@app.route('/empempedit1/<int:CertificateNumber>')
@login_required
def empempedit1(CertificateNumber):
    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                print(f"Fetching CertificateNumber: {CertificateNumber}")  # Debug Print

                cursor.execute("SELECT * FROM form WHERE CertificateNumber = %s", (CertificateNumber,))
                form_details = cursor.fetchone()

                if not form_details:
                    flash("No record found for the given Certificate Number.", "error")
                    return redirect(url_for("empempedit"))  # ✅ Redirect if no record found

                print("Form Details:", form_details)  # Debug Print

                return render_template('empempedit1.html', form=form_details)

    except Exception as e:
        print(f"Error fetching form details: {e}")
        flash("An error occurred while fetching form details.", "error")
        return redirect(url_for("empempedit"))  # ✅ Redirect in case of error

def safe_float(value):
    try:
        return float(value) if value.strip() else None
    except ValueError:
        return None
       
@app.route('/update_form/<int:CertificateNumber>', methods=['POST'])
@login_required
def update_form(CertificateNumber):
    print(f"Received update request for CertificateNumber: {CertificateNumber}")  # Debugging line
    print(request.form.to_dict())  # Debugging line


    try:
        with get_db_connection() as conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                
                # Extract and clean form data
                form_data = {
                    "date": request.form.get("date", "").strip() or None,
                    "applicant_name": request.form.get("applicantName", "").strip() or None,
                    "container_number": request.form.get("containerNumber", "").strip() or None,
                    "size_type": request.form.get("sizeType", "").strip() or None,
                    "tare_weight": request.form.get("tareWeight", "").strip() or None,
                    "payload_capacity": request.form.get("payloadCapacity", "").strip() or None,
                    "declared_total_weight": request.form.get("declaredTotalWeight", "").strip() or None,
                    "stuffing_comm_date_time": request.form.get("stuffingCommDateTime", "").strip() or None,
                    "stuffing_comp_date_time": request.form.get("stuffingCompDateTime", "").strip() or None,
                    "seal_number": request.form.get("sealNumber", "").strip() or None,
                    "port_of_discharge": request.form.get("portOfDischarge", "").strip() or None,
                    "place_of_stuffing": request.form.get("placeOfStuffing", "").strip() or None,
                    "cbm": safe_float(request.form.get("volume", "")),
                    "loading_condition": request.form.get("loadingCondition", "").strip() or None,
                    "lashing": request.form.get("lashing", "").strip() or None,
                    "others": request.form.get("others", "").strip() or None,
                    "weather_condition": request.form.get("weatherCondition", "").strip() or None,
                    "surveyor_name": request.form.get("surveyorName", "").strip() or None,
                    "signature": request.form.get("signature", "").strip() or None,
                    "totalPackages": safe_float(request.form.get("totalPackages", "")),
                    "gross_weight": safe_float(request.form.get("grossWeight", ""))
                }

                # ✅ Determine status based on action
                action = request.form.get("action")
                status = "Draft" if action == "Save as Draft" else "Completed"

                # ✅ Validate required fields only for "Submit"
                if status == "Completed":
                    required_fields = {
                        "date": form_data["date"],
                        "applicant_name": form_data["applicant_name"],
                        "container_number": form_data["container_number"],
                        "surveyor_name": form_data["surveyor_name"]
                    }
                    for field, value in required_fields.items():
                        if not value:
                            flash(f"Error: {field.replace('_', ' ').title()} is required!", "error")
                            return redirect(url_for("empempedit1", CertificateNumber=CertificateNumber))

                # ✅ Retrieve and validate consignment details
                consignment_details = request.form.get("consignmentDetails", "[]").strip()
                try:
                    consignment_details = json.loads(consignment_details)
                    if not isinstance(consignment_details, list):
                        consignment_details = []  # Ensure it's always a list
                except json.JSONDecodeError:
                    consignment_details = []  # Default to empty list if invalid

                # ✅ Update form entry
                update_form_query = """
                    UPDATE form
                    SET date = %s, applicant_name = %s, container_number = %s, size_type = %s, tare_weight = %s, 
                        payload_capacity = %s, declared_total_weight = %s, stuffing_comm_date_time = %s, 
                        stuffing_comp_date_time = %s, seal_number = %s, port_of_discharge = %s, place_of_stuffing = %s, 
                        cbm = %s, loading_condition = %s, lashing = %s, others = %s, 
                        weather_condition = %s, surveyor_name = %s, signature = %s, totalPackages = %s, 
                        consignment_details = %s, status = %s
                    WHERE CertificateNumber = %s
                """
                values = (
                    form_data["date"], form_data["applicant_name"], form_data["container_number"], 
                    form_data["size_type"], form_data["tare_weight"], form_data["payload_capacity"], 
                    form_data["declared_total_weight"], form_data["stuffing_comm_date_time"], 
                    form_data["stuffing_comp_date_time"], form_data["seal_number"], 
                    form_data["port_of_discharge"], form_data["place_of_stuffing"], form_data["cbm"], 
                    form_data["loading_condition"], form_data["lashing"], form_data["others"], 
                    form_data["weather_condition"], form_data["surveyor_name"], form_data["signature"], 
                    form_data["totalPackages"], json.dumps(consignment_details), status, CertificateNumber
                )
                cursor.execute(update_form_query, values)

                # ✅ If submitting, update container and consignment status
                if status == "Completed":
                    update_container_query = """
                        UPDATE container
                        SET status = 'Completed'
                        WHERE container_no = %s AND status = 'In Progress'
                    """
                    cursor.execute(update_container_query, (form_data["container_number"],))

                    # ✅ Update related consignments
                    consignment_ids = [item["id"] for item in consignment_details if "id" in item]
                    if consignment_ids:
                        format_strings = ",".join(["%s"] * len(consignment_ids))
                        update_consignment_query = f"""
                            UPDATE cer
                            SET status = 'Completed'
                            WHERE id IN ({format_strings})
                        """
                        cursor.execute(update_consignment_query, tuple(consignment_ids))

                # ✅ Commit changes
                conn.commit()

                flash("Form saved as draft!" if status == "Draft" else "Form submitted successfully!", "success")
                return redirect(url_for("empdash"))

    except Exception as e:
        print(f"Error updating form: {e}")
        flash(f"An error occurred: {e}", "error")
        return redirect(url_for("empempedit1", CertificateNumber=CertificateNumber))


#####################################################################
#                    <--- Employee FCL--->                          #
#  This section handles form submission, updates database records,  #
#  and ensures data integrity. Admins should review any changes     #
#  carefully before modifying this section.                         #
##########################END########################################



@app.route('/empadd')
def empadd():
    return render_template('empadd.html')

@app.route('/resume')
def resume():
    return render_template('resume.html')

@app.route('/cargo')
def cargo():
    return render_template('cargo.html')

@app.route('/cargoman')
def cargoman():
    return render_template('cargoman.html')

@app.route('/cargomanemp')
def cargomanemp():
    return render_template('cargomanemp.html')

@app.route("/add_cargo", methods=["POST"])
def add_cargo():
    try:
        data = request.get_json()  # Get JSON data from frontend
        conn = get_db_connection()
        cursor = conn.cursor()

        # Insert into database
        query = """
        INSERT INTO cargo (received_date, cfs_name, shipper, destination, invoice_no, invoice_date,
                           invoice_value, total_packages, gross_weight, net_weight, volume, hbl_no, sb_no, sb_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            data["receivedDate"], data["cfsName"], data["shipper"], data["destination"],
            data["invoiceNo"], data["invoiceDate"], data["invoiceValue"], data["totalPackages"],
            data["grossWeight"], data["netWeight"], data["volume"], data["hblNo"], data["sbNo"], data["sbDate"]
        )

        cursor.execute(query, values)
        conn.commit()

        return jsonify({"success": True, "message": "Cargo entry added successfully!"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

    finally:
        cursor.close()
        conn.close()

@app.route("/get_cargo", methods=["GET"])
def get_cargo():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch data from cargo table
        query = "SELECT * FROM cargo ORDER BY id DESC"
        cursor.execute(query)
        cargo_data = cursor.fetchall()

        return jsonify({"success": True, "data": cargo_data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

    finally:
        cursor.close()
        conn.close()

@app.route("/delete_cargo/<int:cargo_id>", methods=["DELETE"])
def delete_cargo(cargo_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete cargo entry by ID
        query = "DELETE FROM cargo WHERE id = %s"
        cursor.execute(query, (cargo_id,))
        conn.commit()

        return jsonify({"success": True, "message": "Cargo entry deleted successfully!"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

    finally:
        cursor.close()
        conn.close()

@app.route("/delete_filtered_cargo", methods=["POST"])
def delete_filtered_cargo():
    try:
        data = request.get_json()
        start_date = data.get("startDate")
        end_date = data.get("endDate")

        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete query with date filter
        query = """
        DELETE FROM cargo
        WHERE received_date BETWEEN %s AND %s
        """
        cursor.execute(query, (start_date, end_date))
        conn.commit()

        return jsonify({"success": True, "message": "Filtered cargo entries deleted successfully!"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

    finally:
        cursor.close()
        conn.close()

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/empdashboard')
def empdashboard():
    return render_template('empdashboard.html')

@app.route('/pic')
def pic():
    return render_template('pic.html')

def increment_alpha_suffix(suffix):
    """ Increment a two-letter alphabetical suffix (AA → AB → AC ... AZ → BA → ZZ) """
    if suffix == "ZZ":
        return "AA"  # Reset to AA after ZZ
    
    first, second = suffix
    alphabet = string.ascii_uppercase

    if second != "Z":  
        return first + alphabet[alphabet.index(second) + 1]  # Increment second letter
    else:  
        return alphabet[alphabet.index(first) + 1] + "A"  # Increment first, reset second

def generate_report_number():
    """ Generate report number in VKM(YEAR,MONTH)AA format with alphabetic increments """
    current_year = datetime.now().year
    current_month = datetime.now().month
    prefix = f"VKM{current_year}{current_month:02}"

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = f"""
                SELECT report_number FROM po 
                WHERE report_number LIKE '{prefix}%'
                ORDER BY report_number DESC 
                LIMIT 1
            """
            cursor.execute(sql)
            result = cursor.fetchone()

        if result and result["report_number"]:
            last_suffix = result["report_number"][-2:]  # Extract last two characters (AA, AB, etc.)
            next_suffix = increment_alpha_suffix(last_suffix)  # Increment alphabetically
        else:
            next_suffix = "AA"  # Start from AA if no records exist

        return f"{prefix}{next_suffix}"
    finally:
        connection.close()

@app.route('/generate_report_number')
def get_report_number():
    report_number = generate_report_number()
    return jsonify({"report_number": report_number})

@app.route('/submit_po', methods=['POST'])
def submit_po():
    company_name = request.form['company_name']
    address = request.form['address']
    phone = request.form['phone']
    gst = request.form['GST']
    status = request.form['status']
    report_number = generate_report_number()  # Auto-generate report number
    submitted_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO po (company_name, address, phone, gst, report_number, status, submitted_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (company_name, address, phone, gst, report_number, status, submitted_at))
        connection.commit()
        flash(f"Form submitted successfully! Report Number: {report_number}", "success")
    except Exception as e:
        print(f"Error: {e}")
        flash("Failed to submit form", "danger")
    finally:
        connection.close()

    return redirect(url_for('po'))

@app.route('/po')
@login_required
def po():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # Fetch all POs
        cursor.execute("SELECT id, company_name, address, phone, gst, report_number, status FROM po ")
        po_data = cursor.fetchall()

        conn.close()

        return render_template('po.html', po_data=po_data)
    except Exception as e:
        print(f"Error: {e}")
        flash('An error occurred while fetching the purchase orders.', 'error')
        return redirect(url_for('po'))






@app.route('/employees', methods=['GET'])
def get_employees():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM employees')
    employees = cursor.fetchall()
    conn.close()
    
    print("Fetched Employees:", employees)  # Debugging line
    return jsonify(employees)  # Returns JSON data

# Route to add a new employee

@app.route('/add_employee', methods=['POST'])
def add_employee():
    conn = None
    cursor = None

    try:
        print("Form Data Received:", request.form)  # Debugging: Print all form data

        # Extract form data
        empId = request.form.get('empId')
        name = request.form.get('name')
        phone = request.form.get('phone')
        address = request.form.get('address')
        role = request.form.get('role')  # Ensure this matches the name attribute in the form
        username = request.form.get('username')
        password = request.form.get('password')

        # Debugging: Print individual form fields
        print("empId:", empId)
        print("name:", name)
        print("phone:", phone)
        print("address:", address)
        print("role:", role)
        print("username:", username)
        print("password:", password)

        # Validate all fields
        if not all([empId, name, phone, address, role, username, password]):
            return jsonify({'error': 'Missing form fields!'}), 400

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()
        conn.begin()

        # Insert into employees table
        cursor.execute('''
            INSERT INTO employees (empId, name, phone, address, role, username, password)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (empId, name, phone, address, role, username, hashed_password))

        # Insert into users table
        cursor.execute('''
            INSERT INTO users (username, password, role)
            VALUES (%s, %s, %s)
        ''', (username, hashed_password, role))

        # Commit the transaction
        conn.commit()
        return jsonify({'message': 'Employee added successfully!'}), 201

    except Exception as e:
        # Rollback in case of error
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500

    finally:
        # Close the cursor and connection
        if cursor:
            cursor.close()
        if conn:
            conn.close()



# Route to delete employees
@app.route('/delete_employees', methods=['POST'])
def delete_employees():
    try:
        data = request.get_json()
        employee_ids = data.get('ids', [])

        # Ensure all IDs are valid integers
        employee_ids = [emp_id for emp_id in employee_ids if emp_id.strip().isdigit()]

        if not employee_ids:
            return jsonify({'error': 'No valid employees selected'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Execute the delete query safely
        query = 'DELETE FROM employees WHERE empId IN ({})'.format(','.join(['%s'] * len(employee_ids)))
        cursor.execute(query, tuple(map(int, employee_ids)))  # Convert IDs to integers before executing

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'message': 'Employees deleted successfully!'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500



if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
