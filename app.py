from flask import Flask, jsonify, render_template, request, redirect, url_for
import mysql.connector
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session
import string
import random
import os
import re


app = Flask(__name__)
app.secret_key = os.urandom(24)

# MySQL 데이터베이스 연결 설정
conn = mysql.connector.connect(
    host="127.0.0.1",      # MySQL 서버 주소
    user="root",        # MySQL 사용자 이름
    password="kwon0822@",    # MySQL 비밀번호
    database="budget_db"    # 사용할 데이터베이스 이름
)
cursor = conn.cursor()

# 홈 페이지 - 거래 내역 조회
@app.route('/index')
@app.route('/index/<int:page>')
def index(page=1):
    
    if 'user_id' not in session:  # 로그인되지 않은 경우
        return redirect(url_for('login'))
    user_id = session['user_id']  # 세션에서 user_id 가져오기
    
    
    items_per_page = 10  # 페이지당 표시할 데이터 개수
    offset = (page - 1) * items_per_page

    # 데이터 조회
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id = %s", (user_id,))
    total_items = cursor.fetchone()[0]
    total_pages = (total_items + items_per_page - 1) // items_per_page

    # 현재 페이지 데이터 가져오기
    cursor.execute(f"""
        SELECT * FROM transactions
        WHERE user_id = %s
        ORDER BY date DESC
        LIMIT {items_per_page} OFFSET {offset}
    """, (user_id,))
    transactions = cursor.fetchall()

    return render_template(
        "index.html",
        transactions=transactions,
        current_page=page,
        total_pages=total_pages
    )

# 거래 추가 페이지
@app.route('/add', methods=["GET", "POST"])
def add_transaction():
    if request.method == "POST":
        
        user_id = session['user_id']  # 세션에서 user_id 가져오기
        date = datetime.now().strftime("%Y-%m-%d")
        amount = int(request.form["amount"])
        category = request.form["category"]
        description = request.form["description"]
        
        # 입력된 금액에 따라 양수/음수로 처리
        transaction_type = request.form["type"]  # 'income' or 'expense'
        if transaction_type == "expense":
            amount = -abs(amount)
        
        cursor.execute('''
            INSERT INTO transactions (date, amount, category, description) 
            VALUES (%s, %s, %s, %s)
            WHERE user_id = %s
        ''', (date, amount, category, description, user_id))
        conn.commit()
        return redirect(url_for('index'))
    return render_template("add.html")

# 거래 수정 페이지
@app.route('/edit/<int:id>', methods=["GET", "POST"])
def edit_transaction(id):
    if request.method == "POST":
        user_id = session['user_id']  # 세션에서 user_id 가져오기
        amount = int(request.form["amount"])
        category = request.form["category"]
        description = request.form["description"]
        cursor.execute('''
            UPDATE transactions SET amount = %s, category = %s, description = %s
            WHERE id = %s AND user_id = %s
        ''', (amount, category, description, id, user_id))
        conn.commit()
        return redirect(url_for('index'))

    cursor.execute("SELECT * FROM transactions WHERE id = %s", (id,))
    transaction = cursor.fetchone()
    return render_template("edit.html", transaction=transaction)

# 거래 삭제
@app.route('/delete/<int:id>')
def delete_transaction(id):
    cursor.execute("DELETE FROM transactions WHERE id = %s", (id,))
    conn.commit()
    return redirect(url_for('index'))

# 통계 화면
@app.route('/stats')
def stats():
    
    user_id = session['user_id']  # 세션에서 user_id 가져오기
    now = datetime.now()
    start_date = now - timedelta(days=2*365)

    # 날짜 범위 계산
    cursor.execute('''
        SELECT 
            DATE_FORMAT(date, '%Y-%m') AS month,
            SUM(amount) AS total
        FROM transactions
        WHERE date >= %s AND user_id = %s
        GROUP BY month
        ORDER BY month
    ''', (start_date, user_id))
    data = cursor.fetchall()
    labels = [row[0] for row in data]  # 월
    values = [float(row[1]) for row in data]  # 월별 합계

    return render_template('stats.html', labels=labels, values=values)

# 통계 세부
@app.route('/stats_data')
def stats_data():
    user_id = session['user_id']  # 세션에서 user_id 가져오기
    range_option = request.args.get('range', '2years')

    # 날짜 범위 계산
    now = datetime.now()
    if range_option == '2years':
        start_date = now - timedelta(days=2 * 365)
    elif range_option == '1year':
        start_date = now - timedelta(days=365)
    elif range_option == '6months':
        start_date = now - timedelta(days=6 * 30)
    elif range_option == '3months':
        start_date = now - timedelta(days=3 * 30)

    # 데이터 가져오기
    cursor.execute('''
        SELECT 
            DATE_FORMAT(date, '%Y-%m') AS month,
            SUM(amount) AS total
        FROM transactions
        WHERE date >= %s AND user_id = %s
        GROUP BY month
        ORDER BY month
    ''', (start_date, user_id))
    data = cursor.fetchall()

    # JSON 데이터 생성
    labels = [row[0] for row in data]
    values = [float(row[1]) for row in data]

    return jsonify({'labels': labels, 'values': values})

# 남은 예산
@app.route('/budget', methods=["GET", "POST"])
def budget():
    # 사용자가 월별 예산을 선택
    if request.method == "POST":
        user_id = session['user_id']  # 세션에서 user_id 가져오기
        year = int(request.form["year"])
        month = int(request.form["month"])

        # 해당 월의 예산 정보 가져오기
        cursor.execute('''
            SELECT budget_amount FROM budgets 
            WHERE year = %s AND month = %s AND user_id = %s
        ''', (year, month, user_id))
        budget_result = cursor.fetchone()

        # 해당 월의 지출 합계 계산
        cursor.execute('''
            SELECT SUM(amount) FROM transactions 
            WHERE YEAR(date) = %s AND MONTH(date) = %s AND amount > 0 AND user_id = %s
        ''', (year, month, user_id))
        total_spent = cursor.fetchone()[0] or 0

        if budget_result:
            budget = budget_result[0]
            remaining = budget - total_spent
        else:
            budget = None
            remaining = None

        return render_template(
            "budget.html",
            selected_year=year,
            selected_month=month,
            budget=budget,
            total_spent=total_spent,
            remaining=remaining
        )
    

    # 초기 화면
    return render_template(
        "budget.html",
        selected_year=None,
        selected_month=None,
        budget=None,
        total_spent=None,
        remaining=None
    )

# 예산 설정
@app.route('/set_budget', methods=["GET", "POST"])
def set_budget():
    if request.method == "POST":
        user_id = session['user_id']  # 세션에서 user_id 가져오기
        year = int(request.form["year"])
        month = int(request.form["month"])
        budget_amount = int(request.form["budget_amount"])

        # 예산 삽입 또는 업데이트
        cursor.execute('''
            INSERT INTO budgets (year, month, budget_amount)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE budget_amount = %s
            WHERE user_id = %s
        ''', (year, month, budget_amount, budget_amount, user_id))
        conn.commit()
        return redirect(url_for('budget'))

    return render_template("set_budget.html")

# 회원가입
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        email = request.form['email']
        
        if len(username) < 7:
            return render_template('register.html', error="아이디는 7자 이상이어야 합니다.")
        
        if not re.match(r"(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{7,}", password):
            return render_template('register.html', error="비밀번호는 7자 이상, 영어, 숫자, 특수문자를 포함해야 합니다.")
        
        cursor.execute('SELECT id FROM users WHERE username = %s OR email = %s', (username, email))
        if cursor.fetchone():
            return "이미 존재하는 사용자명 또는 이메일입니다."
        
        # 새로운 사용자 등록
        cursor.execute('INSERT INTO users (username, password, email) VALUES (%s, %s, %s)',
                       (username, password, email))
        conn.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

# 로그인
@app.route('/', methods=['GET', 'POST'])
def login():
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        
        cursor.execute('SELECT id, password FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="아이디 또는 비밀번호를 확인하세요.")
    return render_template('login.html')


# 비밀번호 변경
@app.route('/change_password', methods=["GET", "POST"])
def change_password():
    
    username = session.get('username')
    
    if request.method == "POST":
        
        current_password = request.form['current_password']
        
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # 데이터베이스에서 현재 사용자 정보 가져오기
        cursor.execute("SELECT password FROM users WHERE username = %s", (username, ))
        user = cursor.fetchone()
        

        # 현재 비밀번호 확인
        if not user or not check_password_hash(user[0], current_password):
            return render_template("change_password.html", error="현재 비밀번호가 올바르지 않습니다.")
        
        if not re.match(r"(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{7,}", new_password):
            return render_template('change_password', error="비밀번호는 7자 이상, 영어, 숫자, 특수문자를 포함해야 합니다.")

        # 새 비밀번호와 확인 비밀번호가 일치하는지 확인
        if new_password != confirm_password:
            return render_template("change_password.html", error="새 비밀번호가 일치하지 않습니다.")

        # 데이터베이스 업데이트
        session.pop('username', None)
        hashed_password = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password = %s WHERE username = %s", (hashed_password, username))
        conn.commit()

        return render_template("change_password.html", success="비밀번호가 성공적으로 변경되었습니다.")

    return render_template("change_password.html")

# 로그아웃
@app.route('/logout')
def logout():
    session.pop('user_id', None)  # 세션에서 사용자 ID 제거
    return redirect(url_for('login'))

# 비밀번호 변경 전 아이디 확인
@app.route('/check_user', methods=["GET", "POST"])
def check_user():
    if request.method == "POST":
        username = request.form['username']

       
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if user:
            # 세션에 사용자 아이디 저장 (아이디 확인 통과)
            session['username'] = username
            return redirect(url_for('change_password'))
        else:
            return render_template("check_user.html", error="존재하지 않는 아이디입니다.")

    return render_template("check_user.html")

# 비밀번호 확인
@app.route('/forgot_password', methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form['username']
        email = request.form['email']

        # 사용자명과 이메일로 사용자 확인
        cursor.execute('SELECT id, email FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()

        if user and user[1] == email:
            # 임시 비밀번호 생성
            temp_password = generate_temp_password()

            # 임시 비밀번호 해싱 후 저장
            hashed_temp_password = generate_password_hash(temp_password)
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_temp_password, user[0]))
            conn.commit()

            # 임시 비밀번호를 템플릿에 전달
            return render_template("forgot_password.html", success="임시 비밀번호가 생성되었습니다. 아래의 임시 비밀번호로 로그인한 후 비밀번호를 변경해주세요.", temp_password=temp_password)

        return render_template("forgot_password.html", error="아이디 또는 이메일이 올바르지 않습니다.")

    return render_template("forgot_password.html")

# 아이디 확인
@app.route('/forgot_id', methods=["GET", "POST"])
def forgot_id():
    if request.method == "POST":

        email = request.form['email']

        # 사용자명과 이메일로 사용자 확인
        cursor.execute('SELECT username FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()

        if user:
            username = user[0]

            # 임시 비밀번호를 템플릿에 전달
            return render_template("forgot_id.html", username=username)

        return render_template("forgot_id.html", error="이메일이 올바르지 않습니다.")

    return render_template("forgot_id.html")


# 특수기호와 영문자를 포함한 임시 비밀번호 생성
def generate_temp_password(length=8):
    characters = string.ascii_letters + string.digits + string.punctuation
    temp_password = ''.join(random.choice(characters) for i in range(length))
    return temp_password



if __name__ == "__main__":
    app.run(debug=True)
