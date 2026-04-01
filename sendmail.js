const axios = require('axios');
const nodemailer = require('nodemailer');
const path = require('path');
const fs = require('fs');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const sendMail = async (userEmail, otp, filePath = null) => {
    const isResultEmail = !!filePath;
    const subject = isResultEmail 
        ? 'Your Colorized Image is Ready!' 
        : `${otp} is your verification code`;
    
    const htmlContent = isResultEmail 
        ? generateResultHTML() 
        : generateOTPHTML(otp);

    const attachments = isResultEmail && fs.existsSync(filePath) ? [{
        filename: path.basename(filePath),
        path: filePath
    }] : [];

    // 1. Try HTTP-Based Service: RESEND
    if (process.env.RESEND_API_KEY) {
        console.log('Using HTTP API: Resend...');
        try {
            const payload = {
                from: 'AI Image Colorizer <onboarding@resend.dev>',
                to: [userEmail],
                subject: subject,
                html: htmlContent
            };
            
            // Note: Resend attachment format might differ, but sticking to basic for now
            // or just using SMTP for attachments as it is more reliable for files
            if (!isResultEmail) {
                const response = await axios.post('https://api.resend.com/emails', payload, {
                    headers: {
                        'Authorization': `Bearer ${process.env.RESEND_API_KEY}`,
                        'Content-Type': 'application/json',
                    }
                });
                console.log('SUCCESS: Email sent via Resend API: ' + response.data.id);
                return true;
            }
        } catch (error) {
            console.error('Resend API Error:', error.response ? error.response.data : error.message);
        }
    }

    // 2. Try HTTP-Based Service: SENDGRID
    if (process.env.SENDGRID_API_KEY && !isResultEmail) {
        console.log('Using HTTP API: SendGrid...');
        try {
            await axios.post('https://api.sendgrid.com/v3/mail/send', {
                personalizations: [{ to: [{ email: userEmail }] }],
                from: { email: process.env.EMAIL_USER || 'no-reply@example.com', name: 'AI Image Colorizer' },
                subject: subject,
                content: [{ type: 'text/html', value: htmlContent }]
            }, {
                headers: {
                    'Authorization': `Bearer ${process.env.SENDGRID_API_KEY}`,
                    'Content-Type': 'application/json',
                }
            });
            console.log('SUCCESS: Email sent via SendGrid API!');
            return true;
        } catch (error) {
            console.error('SendGrid API Error:', error.response ? error.response.data : error.message);
        }
    }

    // 3. Fallback to SMTP: NODEMAILER (Required for attachments)
    const senderEmail = process.env.EMAIL_USER;
    const senderPassword = process.env.EMAIL_PASS;
    const smtpHost = process.env.EMAIL_HOST || 'smtp.gmail.com';
    const smtpPort = parseInt(process.env.EMAIL_PORT || '587');

    if (!senderEmail || !senderPassword) {
        console.error('ERROR: No Email credentials found');
        if (!isResultEmail) logOtpLocally(userEmail, otp);
        process.exit(1);
    }

    console.log(`Using SMTP... (Type: ${isResultEmail ? 'Result' : 'OTP'})`);
    const transporter = nodemailer.createTransport({
        host: smtpHost,
        port: smtpPort,
        secure: smtpPort === 465,
        auth: {
            user: senderEmail,
            pass: senderPassword,
        },
    });

    try {
        const info = await transporter.sendMail({
            from: `"AI Image Colorizer" <${senderEmail}>`,
            to: userEmail,
            subject: subject,
            html: htmlContent,
            attachments: attachments
        });
        console.log('SUCCESS: Email sent via SMTP: ' + info.messageId);
        return true;
    } catch (error) {
        console.error('SMTP ERROR: ' + error.message);
        if (!isResultEmail) logOtpLocally(userEmail, otp);
        if (error.message.includes('Username and Password not accepted')) {
            console.log('\nHINT: If using Gmail, you MUST use an "App Password".');
            console.log('Follow: https://myaccount.google.com/apppasswords');
        }
        process.exit(1);
    }
};

function logOtpLocally(email, otp) {
    const logStr = `\n[${new Date().toISOString()}] OTP for ${email}: ${otp}\n`;
    fs.appendFileSync(path.join(__dirname, 'otp_logs.txt'), logStr);
    console.log('FALLBACK: OTP logged to otp_logs.txt');
}

function generateOTPHTML(otp) {
    return `
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px;">
        <h1 style="color: #6366f1; text-align: center;">AI Image Colorizer</h1>
        <div style="background-color: #f8fafc; padding: 24px; border-radius: 8px;">
            <p>Your verification code is:</p>
            <div style="text-align: center; font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #6366f1; padding: 10px; background: #ede9fe; border-radius: 8px;">
                ${otp}
            </div>
            <p style="margin-top: 20px;">This code expires in 5 minutes.</p>
        </div>
        <div style="margin-top: 20px; font-size: 12px; color: #64748b; text-align: center;">
            If you didn't request this, you can safely ignore this email.
        </div>
    </div>
    `;
}

function generateResultHTML() {
    return `
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px;">
        <h1 style="color: #6366f1; text-align: center;">AI Image Colorizer</h1>
        <div style="background-color: #f8fafc; padding: 24px; border-radius: 8px;">
            <h2 style="color: #1e293b;">Your Image is Ready!</h2>
            <p>Thank you for using AI Colorizer. We've attached your colorized image to this email.</p>
            <p>You can also view it in your dashboard history anytime.</p>
        </div>
        <div style="margin-top: 20px; font-size: 12px; color: #64748b; text-align: center;">
            &copy; 2026 AI Image Colorizer. All rights reserved.
        </div>
    </div>
    `;
}

const emailArg = process.argv[2];
const otpArg = process.argv[3];
const fileArg = process.argv[4]; // Optional file path

if (!emailArg || !otpArg) {
    process.exit(1);
}

sendMail(emailArg, otpArg, fileArg);
