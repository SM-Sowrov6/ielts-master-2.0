import type { Metadata } from "next";
import Link from "next/link";

import { LEGAL_CONTACT, LegalPage } from "@/components/legal/legal-page";

export const metadata: Metadata = { title: "Privacy Policy" };

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy">
      <p>
        This policy explains what personal data IELTS MASTER (&ldquo;we&rdquo;) collects when you
        use our IELTS preparation platform, why we collect it, who processes it for us, and the
        choices you have. We collect only what we need to run the service.
      </p>

      <h2>1. Data we collect</h2>
      <ul>
        <li>
          <strong>Account data:</strong> your name, email address, a securely hashed password (we
          never store the password itself), your confirmation that you meet the minimum age, and the
          versions of these documents you accepted.
        </li>
        <li>
          <strong>Practice data:</strong> your answers in Listening and Reading tests, scores,
          timings and progress.
        </li>
        <li>
          <strong>Writing:</strong> the essays and reports you submit for feedback.
        </li>
        <li>
          <strong>Speaking:</strong> your voice during AI Speaking practice, recordings of your
          answers (when you use recorded practice), and text transcripts of the conversation.
        </li>
        <li>
          <strong>Security data:</strong> session information, a shortened (truncated) form of your
          IP address, browser type, and records of sign-ins and security events. Staff accounts also
          store an encrypted two-factor authentication key.
        </li>
      </ul>
      <p>
        We do not collect payment card details, and we do not sell your personal data or use it for
        advertising.
      </p>

      <h2>2. Why we use it</h2>
      <ul>
        <li>To create and secure your account and keep you signed in.</li>
        <li>To run tests, save your work and show your results and progress.</li>
        <li>
          To give AI feedback on your Writing and Speaking, and to run the AI Speaking examiner.
        </li>
        <li>To send essential emails, such as email verification and password reset.</li>
        <li>To prevent abuse, investigate problems and keep the service working.</li>
      </ul>

      <h2>3. AI processing</h2>
      <p>
        Writing and Speaking feedback is produced by artificial intelligence. Your essays, Speaking
        audio and transcripts are sent to the AI providers listed below only to produce your
        feedback and run the live examiner. AI scores are <strong>estimates</strong> for practice;
        they are not official IELTS results and may contain mistakes. We instruct our systems to
        treat what you write or say as content to assess, never as instructions.
      </p>

      <h2>4. Service providers</h2>
      <p>We use these providers to run the service. They process data on our behalf:</p>
      <ul>
        <li>
          <strong>Google (Gemini API)</strong> — AI evaluation of Writing and Speaking, the AI
          Speaking examiner&rsquo;s voice, and transcription.
        </li>
        <li>
          <strong>LiveKit</strong> — real-time audio connection for AI Speaking practice, and live
          captions of your speech (speech-to-text via LiveKit&rsquo;s inference service).
        </li>
        <li>
          <strong>Cloudflare</strong> — website delivery and security, and storage of audio and
          images (Cloudflare R2).
        </li>
        <li>
          <strong>Oracle Cloud</strong> — the servers that run our application and database.
        </li>
        <li>
          <strong>Our email provider</strong> — sending account emails.
        </li>
      </ul>
      <p>
        Some of these providers process data outside Bangladesh. We choose providers that protect
        data with industry-standard security.
      </p>

      <h2>5. How long we keep data</h2>
      <ul>
        <li>Account and practice data: while your account is active.</li>
        <li>
          Speaking recordings and transcripts: while your account is active, unless you ask us to
          delete them sooner.
        </li>
        <li>
          Security logs: for a limited period needed to protect the service and investigate
          incidents.
        </li>
      </ul>
      <p>
        When you ask us to delete your account, we delete or anonymise your personal data, except
        where we must keep it to meet legal obligations.
      </p>

      <h2>6. Cookies</h2>
      <p>
        We use only strictly necessary cookies: one that keeps you signed in and one that protects
        forms against cross-site request forgery. Your theme choice may be saved in your browser. We
        do not use advertising or tracking cookies.
      </p>

      <h2>7. Security</h2>
      <p>
        Connections are encrypted (HTTPS). Passwords are hashed with Argon2id, sessions can be
        revoked, staff accounts require two-factor authentication, and access to data is limited to
        what each role needs. No system is perfectly secure; if we learn of a breach affecting you,
        we will inform you as required by law.
      </p>

      <h2>8. Your rights</h2>
      <p>
        You can ask us to access, correct, export or delete your personal data, or to stop a
        particular use of it. Email <a href={`mailto:${LEGAL_CONTACT}`}>{LEGAL_CONTACT}</a> from
        your account&rsquo;s email address and we will respond within 30 days. You can change your
        password at any time in your account settings.
      </p>

      <h2>9. Children</h2>
      <p>
        You must meet the minimum age shown at registration to create an account. If we learn that
        an account belongs to someone below that age, we will delete it.
      </p>

      <h2>10. Changes</h2>
      <p>
        If we change this policy in an important way, we will publish a new version and ask you to
        accept it. See also our <Link href="/terms">Terms of Service</Link>.
      </p>

      <h2>11. Contact</h2>
      <p>
        Questions or requests: <a href={`mailto:${LEGAL_CONTACT}`}>{LEGAL_CONTACT}</a>.
      </p>
    </LegalPage>
  );
}
