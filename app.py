from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g
import sqlite3
import os
from datetime import datetime, date, timedelta
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'smartleave_secret_2024'

from datetime import datetime as _dt
def fmt_date(s, fmt='%d %b %Y'):
    if not s: return ''
    try: return _dt.strptime(s[:10], '%Y-%m-%d').strftime(fmt)
    except: return s
app.jinja_env.filters['fmtdate'] = fmt_date
DATABASE = os.path.join(os.path.dirname(__file__), 'smart_leave.db')

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS roles (role_id INTEGER PRIMARY KEY AUTOINCREMENT, role_name TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT, user_code TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        role_id INTEGER NOT NULL, department TEXT, join_date TEXT DEFAULT (date('now')), is_active INTEGER DEFAULT 1,
        FOREIGN KEY (role_id) REFERENCES roles(role_id));
    CREATE TABLE IF NOT EXISTS leave_types (
        leave_type_id INTEGER PRIMARY KEY AUTOINCREMENT, leave_name TEXT NOT NULL,
        max_days_year INTEGER DEFAULT 10, is_paid INTEGER DEFAULT 1,
        allowed_roles TEXT DEFAULT 'Employee');
    CREATE TABLE IF NOT EXISTS leave_applications (
        leave_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, leave_type_id INTEGER NOT NULL,
        start_date TEXT NOT NULL, end_date TEXT NOT NULL, total_days INTEGER NOT NULL, reason TEXT,
        applied_date TEXT DEFAULT (date('now')), current_status TEXT DEFAULT 'Pending',
        FOREIGN KEY (user_id) REFERENCES users(user_id), FOREIGN KEY (leave_type_id) REFERENCES leave_types(leave_type_id));
    CREATE TABLE IF NOT EXISTS leave_status_history (
        history_id INTEGER PRIMARY KEY AUTOINCREMENT, leave_id INTEGER NOT NULL, status TEXT,
        updated_by INTEGER, updated_on TEXT DEFAULT (datetime('now')), remarks TEXT,
        FOREIGN KEY (leave_id) REFERENCES leave_applications(leave_id));
    CREATE TABLE IF NOT EXISTS holidays (
        holiday_id INTEGER PRIMARY KEY AUTOINCREMENT, holiday_date TEXT NOT NULL, description TEXT);
    CREATE TABLE IF NOT EXISTS leave_analysis_results (
        analysis_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, analysis_type TEXT,
        description TEXT, severity_level TEXT, generated_on TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(user_id));
    CREATE TABLE IF NOT EXISTS leave_balances (
        balance_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        leave_type_id INTEGER NOT NULL, year INTEGER NOT NULL,
        allocated_days INTEGER NOT NULL, used_days INTEGER DEFAULT 0,
        UNIQUE(user_id, leave_type_id, year),
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (leave_type_id) REFERENCES leave_types(leave_type_id));
    """)
    db.commit()
    if db.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 0:
        db.execute("INSERT INTO roles (role_name) VALUES ('Admin')")
        db.execute("INSERT INTO roles (role_name) VALUES ('Employee')")
        db.execute("INSERT INTO roles (role_name) VALUES ('Student')")
        db.executemany("INSERT INTO users (user_code,full_name,email,password,role_id,department,join_date) VALUES (?,?,?,?,?,?,?)", [
            ('ADM001','Admin User','admin@smartleave.com','admin123',1,'Administration','2022-01-01'),
            ('EMP001','Rahul Sharma','rahul@smartleave.com','pass123',2,'Computer Science','2023-06-01'),
            ('STU001','Priya Nair','priya@smartleave.com','pass123',3,'B.Tech CSE','2023-08-01'),
        ])
        db.execute("INSERT INTO leave_types (leave_name,max_days_year,is_paid,allowed_roles) VALUES ('Sick Leave',12,1,'Employee')")
        db.execute("INSERT INTO leave_types (leave_name,max_days_year,is_paid,allowed_roles) VALUES ('Casual Leave',8,1,'Employee')")
        db.execute("INSERT INTO leave_types (leave_name,max_days_year,is_paid,allowed_roles) VALUES ('Academic Leave',15,0,'Student')")
        db.execute("INSERT INTO leave_types (leave_name,max_days_year,is_paid,allowed_roles) VALUES ('Medical Leave',10,1,'Student')")
        db.executemany("INSERT INTO holidays (holiday_date,description) VALUES (?,?)", [
            ('2024-01-26','Republic Day'),('2024-08-15','Independence Day'),('2024-10-02','Gandhi Jayanti')
        ])
        db.executemany("INSERT INTO leave_applications (user_id,leave_type_id,start_date,end_date,total_days,reason,applied_date,current_status) VALUES (?,?,?,?,?,?,?,?)", [
            (2,2,'2024-01-01','2024-01-01',1,'Personal work','2023-12-28','Approved'),
            (2,1,'2024-01-08','2024-01-08',1,'Sick','2024-01-07','Approved'),
            (2,2,'2024-01-15','2024-01-15',1,'Personal','2024-01-14','Approved'),
            (2,1,'2024-02-05','2024-02-05',1,'Fever','2024-02-04','Approved'),
            (2,2,'2024-02-12','2024-02-12',1,'Personal','2024-02-11','Approved'),
            (2,1,'2024-03-04','2024-03-05',2,'Flu','2024-03-03','Approved'),
            (2,2,'2024-03-11','2024-03-11',1,'Holiday extension','2024-03-08','Pending'),
            (3,3,'2024-02-01','2024-02-02',2,'Exam preparation','2024-01-30','Approved'),
            (3,4,'2024-03-10','2024-03-10',1,'Doctor visit','2024-03-09','Approved'),
        ])
        db.commit()
    db.close()

def get_user_balances(db, user_id, year=None):
    if year is None:
        year = date.today().year
    role = db.execute("SELECT r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.user_id=?", (user_id,)).fetchone()['role_name']
    leave_types = db.execute("SELECT * FROM leave_types WHERE allowed_roles LIKE ?", (f'%{role}%',)).fetchall()
    balances = []
    for lt in leave_types:
        db.execute("INSERT OR IGNORE INTO leave_balances (user_id, leave_type_id, year, allocated_days, used_days) VALUES (?, ?, ?, ?, 0)",
                   (user_id, lt['leave_type_id'], year, lt['max_days_year']))
        used = db.execute("""SELECT COALESCE(SUM(total_days),0) FROM leave_applications
                             WHERE user_id=? AND leave_type_id=? AND current_status='Approved'
                             AND substr(start_date,1,4)=?""",
                          (user_id, lt['leave_type_id'], str(year))).fetchone()[0]
        db.execute("UPDATE leave_balances SET used_days=? WHERE user_id=? AND leave_type_id=? AND year=?",
                   (used, user_id, lt['leave_type_id'], year))
        balances.append({
            'leave_type_id': lt['leave_type_id'],
            'leave_name': lt['leave_name'],
            'is_paid': lt['is_paid'],
            'allocated': lt['max_days_year'],
            'used': used,
            'remaining': lt['max_days_year'] - used
        })
    db.commit()
    return balances

def login_required(f):
    @wraps(f)
    def d(*a,**kw):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*a,**kw)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a,**kw):
        if 'user_id' not in session: return redirect(url_for('login'))
        if session.get('role') != 'Admin':
            flash('Admin access required.','danger'); return redirect(url_for('dashboard'))
        return f(*a,**kw)
    return d

def parse_date(s): return datetime.strptime(s,'%Y-%m-%d').date()

def calc_working_days(start, end):
    db = get_db()
    holidays = {r['holiday_date'] for r in db.execute("SELECT holiday_date FROM holidays").fetchall()}
    count,cur = 0, start
    while cur <= end:
        if cur.weekday()<5 and cur.strftime('%Y-%m-%d') not in holidays: count+=1
        cur += timedelta(days=1)
    return count

def analyze_patterns(user_id):
    db = get_db()
    apps = [dict(a) for a in db.execute("""
        SELECT la.*,lt.leave_name FROM leave_applications la
        JOIN leave_types lt ON la.leave_type_id=lt.leave_type_id
        WHERE la.user_id=? AND la.current_status='Approved' ORDER BY la.start_date
    """,(user_id,)).fetchall()]
    if not apps: return []
    results = []
    def wd(ds): return parse_date(ds).weekday()

    short=[a for a in apps if a['total_days']==1]
    if len(short)>=7:
        results.append({
            'type':'Frequent Short Leaves','severity':'High',
            'desc':f"{len(short)} single-day leaves found across history.",
            'impact': 'High absenteeism risk. Repeated single-day absences disrupt workflow and may indicate disengagement or avoidance behaviour.',
            'recommendation': 'Not recommended for approval without a valid documented reason. Consider counselling or a formal review meeting.',
            'eligible': False
        })
    elif len(short)>=4:
        results.append({
            'type':'Frequent Short Leaves','severity':'Medium',
            'desc':f"{len(short)} single-day leaves found across history.",
            'impact': 'Moderate concern. Recurring single-day absences may reflect personal issues or scheduling habits.',
            'recommendation': 'Approval is at discretion. Recommend requesting a brief explanation from the applicant.',
            'eligible': True
        })

    mf=[a for a in apps if wd(a['start_date'])==0 or wd(a['end_date'])==4]
    if len(mf)>=3:
        results.append({
            'type':'Weekend Extension Pattern','severity':'Medium',
            'desc':f"{len(mf)} leaves start on Monday or end on Friday.",
            'impact': 'Indicates a pattern of intentionally extending weekends, reducing effective working days.',
            'recommendation': 'Evaluate the current request dates carefully. If this leave also falls on Monday or Friday, extra scrutiny is advised.',
            'eligible': True
        })

    close=sum(1 for i in range(1,len(apps)) if 1<=(parse_date(apps[i]['start_date'])-parse_date(apps[i-1]['end_date'])).days<=7)
    if close>=3:
        results.append({
            'type':'Clustered Leave Pattern','severity':'Medium',
            'desc':f"{close} instances of leaves taken within 7 days of each other.",
            'impact': 'Fragmented and frequent short absences can indicate stress, burnout, or personal instability.',
            'recommendation': 'Recommend discussing workload and wellbeing with the applicant. Conditional approval suggested.',
            'eligible': True
        })

    months={}
    for a in apps:
        m=a['start_date'][:7]
        months[m]=months.get(m,0)+a['total_days']
    heavy=[m for m,d in months.items() if d>=5]
    if heavy:
        results.append({
            'type':'Heavy Leave Months','severity':'Low',
            'desc':f"High leave days in: {', '.join(heavy)}.",
            'impact': 'Concentrated absences in specific months may be seasonal or event-driven.',
            'recommendation': 'Generally acceptable. Monitor if pattern repeats across multiple years.',
            'eligible': True
        })

    # Check total approved days this year vs allocation
    year = date.today().year
    role = db.execute("SELECT r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.user_id=?", (user_id,)).fetchone()['role_name']
    leave_types = db.execute("SELECT * FROM leave_types WHERE allowed_roles LIKE ?", (f'%{role}%',)).fetchall()
    for lt in leave_types:
        used = db.execute("""SELECT COALESCE(SUM(total_days),0) FROM leave_applications
            WHERE user_id=? AND leave_type_id=? AND current_status='Approved' AND substr(start_date,1,4)=?""",
            (user_id, lt['leave_type_id'], str(year))).fetchone()[0]
        remaining = lt['max_days_year'] - used
        if remaining <= 0:
            results.append({
                'type':f'Leave Balance Exhausted — {lt["leave_name"]}','severity':'High',
                'desc':f"All {lt['max_days_year']} allocated days for {lt['leave_name']} have been used this year.",
                'impact': f'No remaining balance for {lt["leave_name"]}. Approving further leaves of this type is outside the standard policy.',
                'recommendation': f'This leave type cannot be approved. Applicant has used all {lt["max_days_year"]} days. Rejection is recommended unless special exception applies.',
                'eligible': False
            })
        elif remaining <= 2:
            results.append({
                'type':f'Low Balance — {lt["leave_name"]}','severity':'Medium',
                'desc':f"Only {remaining} day(s) remaining for {lt['leave_name']} this year.",
                'impact': 'Applicant is approaching their leave limit for this type.',
                'recommendation': 'Approve with caution. Advise applicant to use remaining balance carefully.',
                'eligible': True
            })

    return results


def get_leave_recommendation(user_id, leave_id):
    """Generate a full recommendation report for a specific leave application."""
    db = get_db()
    leave = db.execute("""SELECT la.*,lt.leave_name,lt.max_days_year,u.full_name,u.user_code,r.role_name,u.department
        FROM leave_applications la
        JOIN leave_types lt ON la.leave_type_id=lt.leave_type_id
        JOIN users u ON la.user_id=u.user_id
        JOIN roles r ON u.role_id=r.role_id
        WHERE la.leave_id=?""", (leave_id,)).fetchone()
    if not leave: return None

    patterns = analyze_patterns(user_id)
    high = [p for p in patterns if p['severity']=='High']
    medium = [p for p in patterns if p['severity']=='Medium']
    ineligible = [p for p in patterns if not p.get('eligible', True)]

    # Overall verdict
    if ineligible:
        verdict = 'NOT_RECOMMENDED'
        verdict_label = 'Not Recommended for Approval'
        verdict_reason = ineligible[0]['recommendation']
        verdict_color = 'danger'
    elif len(high) > 0:
        verdict = 'REVIEW_REQUIRED'
        verdict_label = 'Review Required Before Approval'
        verdict_reason = 'High severity patterns detected. Admin review and justification required.'
        verdict_color = 'warning'
    elif len(medium) > 0:
        verdict = 'CONDITIONAL'
        verdict_label = 'Conditionally Recommendable'
        verdict_reason = 'Some patterns detected. Approval is at discretion with awareness of the patterns.'
        verdict_color = 'info'
    else:
        verdict = 'RECOMMENDED'
        verdict_label = 'Recommended for Approval'
        verdict_reason = 'No concerning patterns detected. Leave history is healthy.'
        verdict_color = 'success'

    # Balance check for this specific leave type
    year = date.today().year
    used = db.execute("""SELECT COALESCE(SUM(total_days),0) FROM leave_applications
        WHERE user_id=? AND leave_type_id=? AND current_status='Approved' AND substr(start_date,1,4)=?""",
        (user_id, leave['leave_type_id'], str(year))).fetchone()[0]
    remaining = leave['max_days_year'] - used
    total_apps = db.execute("SELECT COUNT(*) FROM leave_applications WHERE user_id=?", (user_id,)).fetchone()[0]
    approved_count = db.execute("SELECT COUNT(*) FROM leave_applications WHERE user_id=? AND current_status='Approved'", (user_id,)).fetchone()[0]
    approval_rate = round((approved_count / total_apps * 100) if total_apps > 0 else 0)

    return {
        'leave': dict(leave),
        'patterns': patterns,
        'verdict': verdict,
        'verdict_label': verdict_label,
        'verdict_reason': verdict_reason,
        'verdict_color': verdict_color,
        'balance': {'used': used, 'remaining': remaining, 'allocated': leave['max_days_year']},
        'stats': {'total_apps': total_apps, 'approved': approved_count, 'approval_rate': approval_rate}
    }

@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        db=get_db()
        user=db.execute("SELECT u.*,r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.email=? AND u.password=? AND u.is_active=1",
            (request.form['email'],request.form['password'])).fetchone()
        if user:
            session['user_id']=user['user_id']; session['user_name']=user['full_name']
            session['role']=user['role_name']; session['user_code']=user['user_code']
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.','danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        db = get_db()
        email = request.form.get('email')
        user_code = request.form.get('user_code')
        
        user = db.execute("SELECT * FROM users WHERE email=? AND user_code=? AND is_active=1", 
                          (email, user_code)).fetchone()
        
        if user:
            session['reset_user_id'] = user['user_id']
            return redirect(url_for('reset_password'))
        else:
            flash('Invalid email or user code. Verification failed.', 'danger')
            
    return render_template('forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if 'reset_user_id' not in session:
        flash('Unauthorized access. Please verify your details first.', 'danger')
        return redirect(url_for('forgot_password'))
        
    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html')
            
        db = get_db()
        db.execute("UPDATE users SET password=? WHERE user_id=?", 
                   (new_password, session['reset_user_id']))
        db.commit()
        
        session.pop('reset_user_id', None)
        flash('Password updated successfully. You can now login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('reset_password.html')

@app.route('/dashboard')
@login_required
def dashboard():
    db=get_db()
    user=db.execute("SELECT u.*,r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.user_id=?",(session['user_id'],)).fetchone()
    if session['role']=='Admin':
        total_users=db.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]
        total_employees=db.execute("SELECT COUNT(*) FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.is_active=1 AND r.role_name='Employee'").fetchone()[0]
        total_students=db.execute("SELECT COUNT(*) FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.is_active=1 AND r.role_name='Student'").fetchone()[0]
        pending=db.execute("SELECT COUNT(*) FROM leave_applications WHERE current_status='Pending'").fetchone()[0]
        approved_today=db.execute("SELECT COUNT(*) FROM leave_applications WHERE current_status='Approved' AND applied_date=?",(date.today().isoformat(),)).fetchone()[0]
        recent=db.execute("SELECT la.*,lt.leave_name,u.full_name,u.user_code,r.role_name FROM leave_applications la JOIN leave_types lt ON la.leave_type_id=lt.leave_type_id JOIN users u ON la.user_id=u.user_id JOIN roles r ON u.role_id=r.role_id ORDER BY la.applied_date DESC LIMIT 5").fetchall()
        all_users = db.execute("SELECT u.user_id,u.full_name,u.user_code,r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.is_active=1 AND r.role_name!='Admin'").fetchall()
        user_alerts = []
        for u in all_users:
            pts = analyze_patterns(u['user_id'])
            high = [p for p in pts if p['severity'] in ('High','Medium')]
            if high:
                user_alerts.append({'name':u['full_name'],'code':u['user_code'],'role':u['role_name'],'count':len(pts),'uid':u['user_id'],'top':high[0]['type']})
        return render_template('dashboard_admin.html',total_users=total_users,total_employees=total_employees,total_students=total_students,pending=pending,approved_today=approved_today,recent=recent,user=user,user_alerts=user_alerts)
    else:
        my_apps=db.execute("SELECT la.*,lt.leave_name FROM leave_applications la JOIN leave_types lt ON la.leave_type_id=lt.leave_type_id WHERE la.user_id=? ORDER BY la.applied_date DESC LIMIT 5",(session['user_id'],)).fetchall()
        pending_count=db.execute("SELECT COUNT(*) FROM leave_applications WHERE user_id=? AND current_status='Pending'",(session['user_id'],)).fetchone()[0]
        approved_count=db.execute("SELECT COUNT(*) FROM leave_applications WHERE user_id=? AND current_status='Approved'",(session['user_id'],)).fetchone()[0]
        balances = get_user_balances(db, session['user_id'])
        patterns = analyze_patterns(session['user_id'])
        return render_template('dashboard_user.html',my_apps=my_apps,pending_count=pending_count,approved_count=approved_count,user=user,balances=balances,patterns=patterns)

@app.route('/apply-leave', methods=['GET','POST'])
@login_required
def apply_leave():
    db=get_db()
    role = session['role']
    leave_types = db.execute("SELECT * FROM leave_types WHERE allowed_roles LIKE ?", (f'%{role}%',)).fetchall()
    balances = get_user_balances(db, session['user_id'])
    balance_map = {b['leave_type_id']: b for b in balances}
    today = date.today().isoformat()
    if request.method=='POST':
        lt_id = int(request.form['leave_type_id'])
        start=parse_date(request.form['start_date']); end=parse_date(request.form['end_date'])
        if end<start:
            flash('End date cannot be before start date.','danger')
            return render_template('apply_leave.html',leave_types=leave_types,balance_map=balance_map,today=today)
        total=calc_working_days(start,end)
        if total==0:
            flash('Selected dates fall on weekends/holidays.','warning')
            return render_template('apply_leave.html',leave_types=leave_types,balance_map=balance_map,today=today)
        bal = balance_map.get(lt_id)
        if bal and total > bal['remaining']:
            flash(f'Insufficient balance! You have only {bal["remaining"]} day(s) remaining for {bal["leave_name"]}.','danger')
            return render_template('apply_leave.html',leave_types=leave_types,balance_map=balance_map,today=today)
        cur=db.execute("INSERT INTO leave_applications (user_id,leave_type_id,start_date,end_date,total_days,reason,applied_date,current_status) VALUES (?,?,?,?,?,?,?,?)",
            (session['user_id'],lt_id,start.isoformat(),end.isoformat(),total,request.form['reason'],date.today().isoformat(),'Pending'))
        db.execute("INSERT INTO leave_status_history (leave_id,status,updated_by,remarks) VALUES (?,?,?,?)",(cur.lastrowid,'Pending',session['user_id'],'Application submitted'))
        db.commit()
        patterns = analyze_patterns(session['user_id'])
        db.execute("DELETE FROM leave_analysis_results WHERE user_id=?",(session['user_id'],))
        for p in patterns:
            db.execute("INSERT INTO leave_analysis_results (user_id,analysis_type,description,severity_level) VALUES (?,?,?,?)",
                       (session['user_id'],p['type'],p['desc'],p['severity']))
        db.commit()
        flash(f'Leave applied for {total} working day(s).','success')
        high_patterns = [p for p in patterns if p['severity']=='High']
        if high_patterns:
            flash(f'⚠️ Pattern Alert: {high_patterns[0]["type"]} detected. Please review your leave patterns.','warning')
        return redirect(url_for('my_leaves'))
    return render_template('apply_leave.html',leave_types=leave_types,balance_map=balance_map,today=today)

@app.route('/my-leaves')
@login_required
def my_leaves():
    db=get_db()
    apps=db.execute("SELECT la.*,lt.leave_name FROM leave_applications la JOIN leave_types lt ON la.leave_type_id=lt.leave_type_id WHERE la.user_id=? ORDER BY la.applied_date DESC",(session['user_id'],)).fetchall()
    balances = get_user_balances(db, session['user_id'])
    return render_template('my_leaves.html',applications=apps,balances=balances)

@app.route('/manage-leaves')
@admin_required
def manage_leaves():
    db=get_db(); sf=request.args.get('status','all')
    q="SELECT la.*,lt.leave_name,u.full_name,u.department,r.role_name FROM leave_applications la JOIN leave_types lt ON la.leave_type_id=lt.leave_type_id JOIN users u ON la.user_id=u.user_id JOIN roles r ON u.role_id=r.role_id"
    apps=db.execute(q+(" WHERE la.current_status=? ORDER BY la.applied_date DESC" if sf!='all' else " ORDER BY la.applied_date DESC"),(sf.capitalize(),) if sf!='all' else ()).fetchall()
    return render_template('manage_leaves.html',applications=apps,status_filter=sf)

@app.route('/update-leave/<int:leave_id>',methods=['POST'])
@admin_required
def update_leave(leave_id):
    db=get_db(); action=request.form['action']; remarks=request.form.get('remarks','')
    ns='Approved' if action=='approve' else 'Rejected'
    db.execute("UPDATE leave_applications SET current_status=? WHERE leave_id=?",(ns,leave_id))
    db.execute("INSERT INTO leave_status_history (leave_id,status,updated_by,remarks) VALUES (?,?,?,?)",(leave_id,ns,session['user_id'],remarks))
    db.commit(); flash(f'Leave {ns.lower()} successfully.','success'); return redirect(url_for('manage_leaves'))

@app.route('/analysis')
@login_required
def analysis():
    db=get_db()
    user=db.execute("SELECT u.*,r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.user_id=?",(session['user_id'],)).fetchone()
    if session['role']=='Admin':
        users=db.execute("SELECT u.*,r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.is_active=1 AND r.role_name!='Admin'").fetchall()
        return render_template('analysis_admin.html',users=users,user=user)
    patterns=analyze_patterns(session['user_id'])
    db.execute("DELETE FROM leave_analysis_results WHERE user_id=?",(session['user_id'],))
    for p in patterns:
        db.execute("INSERT INTO leave_analysis_results (user_id,analysis_type,description,severity_level) VALUES (?,?,?,?)",(session['user_id'],p['type'],p['desc'],p['severity']))
    db.commit()
    apps=db.execute("SELECT la.*,lt.leave_name FROM leave_applications la JOIN leave_types lt ON la.leave_type_id=lt.leave_type_id WHERE la.user_id=? AND la.current_status='Approved' ORDER BY la.start_date",(session['user_id'],)).fetchall()
    balances = get_user_balances(db, session['user_id'])
    return render_template('analysis_user.html',patterns=patterns,applications=apps,user=user,balances=balances)

@app.route('/api/analyze/<int:user_id>')
@admin_required
def api_analyze(user_id):
    db=get_db()
    user=db.execute("SELECT * FROM users WHERE user_id=?",(user_id,)).fetchone()
    if not user: return jsonify({'error':'Not found'}),404
    patterns=analyze_patterns(user_id)
    db.execute("DELETE FROM leave_analysis_results WHERE user_id=?",(user_id,))
    for p in patterns:
        db.execute("INSERT INTO leave_analysis_results (user_id,analysis_type,description,severity_level) VALUES (?,?,?,?)",(user_id,p['type'],p['desc'],p['severity']))
    db.commit()
    apps=db.execute("SELECT la.*,lt.leave_name FROM leave_applications la JOIN leave_types lt ON la.leave_type_id=lt.leave_type_id WHERE la.user_id=? AND la.current_status='Approved'",(user_id,)).fetchall()
    return jsonify({'user':user['full_name'],'patterns':patterns,'leave_data':[{'month':a['start_date'][:7],'days':a['total_days'],'type':a['leave_name']} for a in apps]})

@app.route('/api/leave-review/<int:leave_id>')
@admin_required
def api_leave_review(leave_id):
    db=get_db()
    leave=db.execute("SELECT * FROM leave_applications WHERE leave_id=?",(leave_id,)).fetchone()
    if not leave: return jsonify({'error':'Not found'}),404
    report = get_leave_recommendation(leave['user_id'], leave_id)
    if not report: return jsonify({'error':'Could not generate report'}),500
    return jsonify(report)

@app.route('/api/leave-stats')
@login_required
def api_leave_stats():
    db=get_db()
    if session['role']=='Admin':
        apps=db.execute("SELECT la.*,lt.leave_name FROM leave_applications la JOIN leave_types lt ON la.leave_type_id=lt.leave_type_id WHERE la.current_status='Approved'").fetchall()
    else:
        apps=db.execute("SELECT la.*,lt.leave_name FROM leave_applications la JOIN leave_types lt ON la.leave_type_id=lt.leave_type_id WHERE la.user_id=? AND la.current_status='Approved'",(session['user_id'],)).fetchall()
    from collections import Counter,defaultdict
    monthly=defaultdict(int)
    for a in apps: monthly[a['start_date'][:7]]+=a['total_days']
    return jsonify({'monthly':dict(sorted(monthly.items())),'by_type':dict(Counter(a['leave_name'] for a in apps))})

@app.route('/users')
@admin_required
def manage_users():
    db=get_db()
    return render_template('manage_users.html',
        users=db.execute("SELECT u.*,r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.is_active=1").fetchall(),
        roles=db.execute("SELECT * FROM roles WHERE role_name!='Admin'").fetchall())

@app.route('/add-user',methods=['POST'])
@admin_required
def add_user():
    db=get_db()
    db.execute("INSERT INTO users (user_code,full_name,email,password,role_id,department,join_date) VALUES (?,?,?,?,?,?,?)",
        (request.form['user_code'],request.form['full_name'],request.form['email'],request.form['password'],int(request.form['role_id']),request.form['department'],request.form['join_date']))
    db.commit(); flash('User added successfully.','success'); return redirect(url_for('manage_users'))

@app.route('/deactivate-user/<int:user_id>', methods=['POST'])
@admin_required
def deactivate_user(user_id):
    db=get_db()
    db.execute("UPDATE users SET is_active=0 WHERE user_id=?", (user_id,))
    db.commit(); flash('User deactivated.','success'); return redirect(url_for('manage_users'))

@app.route('/profile')
@login_required
def profile():
    db=get_db()
    user=db.execute("SELECT u.*,r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.user_id=?",(session['user_id'],)).fetchone()
    total=db.execute("SELECT COUNT(*) FROM leave_applications WHERE user_id=?",(session['user_id'],)).fetchone()[0]
    approved=db.execute("SELECT COUNT(*) FROM leave_applications WHERE user_id=? AND current_status='Approved'",(session['user_id'],)).fetchone()[0]
    pending=db.execute("SELECT COUNT(*) FROM leave_applications WHERE user_id=? AND current_status='Pending'",(session['user_id'],)).fetchone()[0]
    balances = get_user_balances(db, session['user_id'])
    return render_template('profile.html',user=user,total_leaves=total,approved=approved,pending=pending,balances=balances)

if __name__=='__main__':
    init_db()
    app.run(debug=True)
