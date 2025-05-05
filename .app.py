import os
import io
import base64
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

import boto3
import stripe
from botocore.exceptions import ClientError
from flask import (
    Flask, render_template, redirect, url_for,
    request, jsonify, session
)
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user
)

# ─── App & Config ──────────────────────────────────────────────────────────────
app = Flask(__name__)
# Embed your secrets directly (not recommended for production)
app.secret_key = "KGNKwuBzf2GTBilMJmODYF7ewD0i1j2uRpho6YkEg9"

# Env vars with defaults and literal fallbacks
DYNAMO_TABLE    = "tweenleaf-users"
STRIPE_SECRET   = "sk_test_51RKKt9CS2zzOISLkcTrdcy0oiXgMurKGNKwuBzf2GTBilMJmODYF7ewD0i1j2uRpho6YkEg9pAkeRVhe2vFy100Wug1dc6Y"
WEBHOOK_SECRET  = "whsec_V5OAiFCO7V1gZ924ZOwAbaM3XMdCczKG"
PORTAL_CONFIG   = "bpc_1RKQ6PCS2zzOISLk8ReKuKO8"

# Initialize AWS & Stripe
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table    = dynamodb.Table(DYNAMO_TABLE)

cw = boto3.client("cloudwatch", region_name="us-east-1")
stripe.api_key = STRIPE_SECRET

# Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, email):
        self.id = email

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def get_usage_chart(user_id):
    now   = datetime.utcnow()
    start = now - timedelta(hours=24)
    resp = cw.get_metric_data(
        MetricDataQueries=[{
            "Id": "runs",
            "MetricStat": {
                "Metric": {
                    "Namespace": "Tweenleaf",
                    "MetricName": "RunsPerHour",
                    "Dimensions": [{"Name": "UserId", "Value": user_id}]
                },
                "Period": 3600,
                "Stat": "Sum",
            },
            "ReturnData": True,
        }],
        StartTime=start,
        EndTime=now,
    )
    data = resp["MetricDataResults"][0]
    ts, vals = data["Timestamps"], data["Values"]

    plt.figure()
    plt.plot(ts, vals)
    plt.title("Runs per Hour (last 24h)")
    plt.xlabel("Time UTC")
    plt.ylabel("Count")

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("ascii")
    plt.close()
    return img_b64

# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health_check():
    return "OK", 200

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")
    data = request.json
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    item = {
        "userId": user_id,
        "tier": "free",
        "runsToday": 0,
        "lastReset": datetime.utcnow().date().isoformat()
    }
    try:
        table.put_item(Item=item)
    except ClientError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"message": "user created", "user_id": user_id}), 201

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    email = request.form["email"]
    login_user(User(email))
    return redirect(url_for("dashboard"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    email = session.get("_user_id")
    resp = table.get_item(Key={"userId": email})
    item = resp.get("Item", {})
    tier      = item.get("tier", "free")
    runs      = int(item.get("runsToday", 0))
    allowance = 5 if tier == "free" else 10
    last_reset= item.get("lastReset", "never")
    chart     = get_usage_chart(email)
    return render_template(
        "dashboard.html",
        email=email,
        tier=tier,
        runs=runs,
        allowance=allowance,
        last_reset=last_reset,
        chart=chart
    )

@app.route("/portal")
@login_required
def portal():
    customer_email = session.get("_user_id")
    session_obj = stripe.billing_portal.Session.create(
        configuration=PORTAL_CONFIG,
        customer_email=customer_email,
        return_url=url_for("dashboard", _external=True)
    )
    return redirect(session_obj.url, code=303)

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload    = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, WEBHOOK_SECRET
        )
    except ValueError:
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        return "Invalid signature", 400
    if event["type"] == "customer.subscription.updated":
        sub        = event["data"]["object"]
        email      = sub["customer_email"]
        plan_price = sub["items"]["data"][0]["plan"]["id"]
        tier = "basic" if plan_price == "price_1RKLNsCS2zzOISLkStFc2hmJ" else "pro"
        table.update_item(
            Key={"userId": email},
            UpdateExpression="SET tier = :t",
            ExpressionAttributeValues={":t": tier}
        )
    elif event["type"] == "customer.subscription.deleted":
        sub   = event["data"]["object"]
        email = sub["customer_email"]
        table.update_item(
            Key={"userId": email},
            UpdateExpression="SET tier = :t",
            ExpressionAttributeValues={":t": "free"}
        )
    return jsonify({"status": "success"}), 200

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
