import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
import pandas as pd

app = Flask(__name__)

# ==========================================
# [設定區]
# ==========================================
class Config:
    DB_NAME = 'feedback_data.db'
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_key_123')

    # === Gmail 設定 (Google Mail) ===
    SMTP_SERVER = 'smtp.gmail.com'
    SMTP_PORT = 465  # Gmail SSL 專用埠
    
    # 讀取 Render 環境變數
    SENDER_EMAIL = os.environ.get('SENDER_EMAIL') 
    SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')

    # === 部門 Email 對照表 ===
    DEPT_MAILS = {
        '5542': ['S21610@chipmos.com'],
        'HR': ['hr@chipmos.com'] 
    }

app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{Config.DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# 資料庫模型
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
# 核心功能
# ==========================================
def auto_classify(comment):
    comment = comment.lower() if comment else ""
    if any(x in comment for x in ['慢', '差', '生氣', '爛']): return "緊急客訴 (Urgent)"
    elif any(x in comment for x in ['讚', '好', '喜歡', '棒']): return "正面好評 (Positive)"
    elif any(x in comment for x in ['建議', '希望', '可以']): return "產品建議 (Suggestion)"
    else: return "一般回饋 (General)"

def send_notification_email(data, target_emails):
    if not Config.SENDER_EMAIL or not Config.SENDER_PASSWORD:
        print(">> 系統警告：未設定 Email 環境變數，無法寄信。")
        return False

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
    (此為 Render 雲端自動發信)
    """
    
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = Config.SENDER_EMAIL
        msg['To'] = ", ".join(target_emails)

        # === 關鍵修改：Gmail SSL 連線 ===
        server = smtplib.SMTP_SSL(Config.SMTP_SERVER, Config.SMTP_PORT, timeout=10)
        server.login(Config.SENDER_EMAIL, Config.SENDER_PASSWORD)
        server.sendmail(Config.SENDER_EMAIL, target_emails, msg.as_string())
        server.quit()
        
        print(f">> Gmail 已寄送至: {target_emails}")
        return True
    except Exception as e:
        print(f">> Email 發送失敗: {e}")
        return False

# ==========================================
# 網頁路由
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
        
        if department in Config.DEPT_MAILS:
            target_emails = Config.DEPT_MAILS[department]
            try:
                success = send_notification_email({
                    'name': name,
                    'department': department,
                    'rating': rating,
                    'comment': comment,
                    'category': category
                }, target_emails)
                
                if success:
                    flash(f'感謝！通知已發送至 {department} (Gmail發送)。', 'success')
                else:
                    flash('回饋已儲存，但 Email 發送失敗。', 'error')
            except Exception as e:
                print(f"Error: {e}")
                flash('回饋已儲存，但通知系統異常。', 'error')
        else:
            flash('感謝您的回饋！(此部門未設定通知信箱)', 'success')
            
        return redirect(url_for('index'))

    departments = Config.DEPT_MAILS.keys()
    return render_template('index.html', departments=departments)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == 'admin' and request.form.get('password') == '1234':
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        flash('帳號或密碼錯誤', 'error')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'): return redirect(url_for('login'))
    stats = get_analytics_data()
    return render_template('dashboard.html', stats=stats)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
