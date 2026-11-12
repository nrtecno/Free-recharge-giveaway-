
const form = document.getElementById("registrationForm");

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const phone = document.getElementById("phone").value.trim();
    const operator = document.getElementById("operator").value;
    const consent = document.getElementById("consent").checked;
    const result = document.getElementById("result");
    const button = form.querySelector("button");

    if (!/^[6-9]\d{9}$/.test(phone)) {
      alert("कृपया सही 10 अंकों का मोबाइल नंबर डालें।");
      return;
    }

    if (!operator || !consent) {
      alert("सभी जानकारी और सहमति जरूरी है।");
      return;
    }

    button.disabled = true;
    button.textContent = "आवेदन जमा हो रहा है...";

    try {
      const response = await fetch("/api/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          phone,
          operator,
          consent,
          campaign_id: CAMPAIGN_ID
        })
      });

      const data = await response.json();

      result.hidden = false;

      if (!response.ok) {
        result.textContent = data.error || "आवेदन जमा नहीं हुआ।";
        return;
      }

      form.hidden = true;
      result.textContent =
        "🎉 आपका आवेदन सफलतापूर्वक जमा हो गया है। " +
        "Registration ID: " + data.registration_id +
        ". रिचार्ज की पुष्टि आयोजक द्वारा की जाएगी।";

    } catch (error) {
      result.hidden = false;
      result.textContent = "नेटवर्क समस्या। दोबारा कोशिश करें।";
    } finally {
      button.disabled = false;
      button.textContent = "🎁 आवेदन जमा करें";
    }
  });
}
