import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
import pandas as pd

app = Flask(__name__)

# ==========================================
# [使用者參數設定區]
# ==========================================
class Config:
    DB_NAME = 'feedback_data.db'
    
    # # 1. Email 發信伺服器設定
    # SMTP_SERVER = 'smtp.gmail.com'
    # SMTP_PORT = 587
    # SENDER_EMAIL = 'toby771213@gmail.com' 
    # SENDER_PASSWORD = 'qpjp aubx vlte vyvy' 

    # === Apple iCloud / @me.com 設定 ===
    SMTP_SERVER = 'smtp.mail.me.com'
    SMTP_PORT = 587
    SENDER_EMAIL = 'toby1213@me.com'     
    # 剛剛申請到的 Apple App 專用密碼
    SENDER_PASSWORD = 'vxam-nfle-biuz-qsgb'


    # 2. Session 安全密鑰
    SECRET_KEY = 'super_secret_key_dont_share'

    # 3. 後台登入帳號密碼
    USERS = {
        'S17081': '0960234600',      
        'S23072': '0932615118',     
        'S5801': '0932674727',
        'S17734': '1223334444',
        'S27358': '1223334444',
        'S22962': '1223334444',
        'S21610': '0960550739'         
    }

    # 4. ### 修改重點：部門與主管 Email 對照表 (支援多人) ###
    # 規則：請用中括號 [] 把 Email 包起來，中間用逗號隔開
    DEPT_MAILS = {
        # '5540': ['S17081@chipmos.com', 'S23072@chipmos.com', '@chipmos.com'],  # 三人收信
        # '5541': ['@chipmos.com'],   # 即便只有一人，建議也用 [] 包起來保持格式統一
        '5542':   ['S21610@chipmos.com']
        # '5545': ['S17734@chipmos.com']     # 預設/備用
    }

app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{Config.DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# 資料庫模型 (無須變動)
# ==========================================
class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50), nullable=False) 
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ==========================================
# 核心功能函式
# ==========================================
def auto_classify(comment):
    comment = comment.lower() if comment else ""
    if any(x in comment for x in ['慢', '差', '生氣', '爛']): return "緊急客訴 (Urgent)"
    elif any(x in comment for x in ['讚', '好', '喜歡', '棒']): return "正面好評 (Positive)"
    elif any(x in comment for x in ['建議', '希望', '可以']): return "產品建議 (Suggestion)"
    else: return "一般回饋 (General)"

# ### 修改重點：升級版寄信功能 (處理列表) ###
def send_notification_email(data, target_emails):
    """
    target_emails: 現在這是一個包含多個 Email 的列表 (List)
    """
    
    # 防呆機制：如果傳進來的不是列表(只是單個字串)，把它變成列表，避免程式出錯
    if isinstance(target_emails, str):
        target_emails = [target_emails]

    subject = f"【{data['department']}部門通知】新問卷：{data['category']} - 來自 {data['name']}"
    body = f"""
    部門主管您好，收到一筆歸屬於貴部門的問卷：
    -----------------------------
    部門：{data['department']}
    姓名：{data['name']}
    評分：{data['rating']} 星
    系統分類：{data['category']}
    內容：{data['comment']}
    -----------------------------
    """
    
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = Config.SENDER_EMAIL
        msg['To'] = ", ".join(target_emails) 

        # === 修改開始：改用 SSL 連線 (Port 465) ===
        # 原本是 server = smtplib.SMTP(..., 587)
        # 現在改成 SMTP_SSL，並且使用 465 Port
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        
        # 注意：SSL 模式不需要 server.starttls()，直接登入即可
        server.login(Config.SENDER_EMAIL, Config.SENDER_PASSWORD)
        
        server.sendmail(Config.SENDER_EMAIL, target_emails, msg.as_string())
        server.quit()
        # === 修改結束 ===

        print(f">> Email 已群發至: {target_emails}")
    except Exception as e:
        print(f">> Email 發送失敗: {e}")

def get_analytics_data():
    try:
        df = pd.read_sql(Feedback.query.statement, db.session.connection())
        if df.empty: return {'avg_rating': 0, 'count': 0, 'category_counts': {}}
        return {
            'avg_rating': round(df['rating'].mean(), 1),
            'count': len(df),
            'category_counts': df['category'].value_counts().to_dict()
        }
    except Exception:
        return {'avg_rating': 0, 'count': 0, 'category_counts': {}}

# ==========================================
# 網頁路由 (Routes)
# ==========================================

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        name = request.form.get('name')
        department = request.form.get('department')
        rating = int(request.form.get('rating'))
        comment = request.form.get('comment')
        category = auto_classify(comment)
        
        new_feedback = Feedback(name=name, department=department, rating=rating, comment=comment, category=category)
        db.session.add(new_feedback)
        db.session.commit()
        
        # === 修改重點開始 ===
        # 確保部門代號存在於設定檔中才寄信
        if department in Config.DEPT_MAILS:
            manager_emails = Config.DEPT_MAILS[department]
            
            send_notification_email({
                'name': name,
                'department': department,
                'rating': rating,
                'comment': comment,
                'category': category
            }, manager_emails) 
        # === 修改重點結束 ===
        
        flash(f'感謝您的回饋！通知已發送至 {department} 部門主管群。', 'success')
        return redirect(url_for('index'))

    departments = Config.DEPT_MAILS.keys()
    return render_template('index.html', departments=departments)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        input_user = request.form.get('username')
        input_pwd = request.form.get('password')
        
        if input_user in Config.USERS and Config.USERS[input_user] == input_pwd:
            session['logged_in'] = True
            session['username'] = input_user
            flash(f'歡迎回來，{input_user}！', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('帳號或密碼錯誤', 'error')
            
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    current_user = session.get('username')
    stats = get_analytics_data()
    return render_template('dashboard.html', stats=stats, current_user=current_user)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)