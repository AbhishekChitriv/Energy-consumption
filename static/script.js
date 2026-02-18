document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('predictionForm');
    const resultContainer = document.getElementById('result');
    const predictionValue = document.getElementById('predictionValue');
    const predictBtn = document.getElementById('predictBtn');
    const btnText = predictBtn.querySelector('.btn-text');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // UI Loading State
        const originalBtnText = btnText.textContent;
        btnText.textContent = 'Calculating...';
        predictBtn.disabled = true;
        resultContainer.classList.remove('show');

        // Gather data
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());

        try {
            const response = await fetch('/predict', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data),
            });

            const result = await response.json();

            if (result.status === 'success') {
                // Formatting the number
                const prediction = parseFloat(result.prediction).toFixed(2);

                // Animate count up (simplified)
                predictionValue.textContent = prediction;

                resultContainer.classList.remove('hidden');
                // Small delay to allow display:block to apply before opacity transition
                setTimeout(() => {
                    resultContainer.classList.add('show');
                }, 10);
            } else {
                alert('Error: ' + result.message);
            }

        } catch (error) {
            console.error('Error:', error);
            alert('An error occurred while fetching the prediction.');
        } finally {
            // Restore UI
            btnText.textContent = originalBtnText;
            predictBtn.disabled = false;
        }
    });
});
