// Örneğin, seans seçiminde 1. Kat için Akşam seansını gizlemek
document.addEventListener('DOMContentLoaded', function() {
    const katSelect = document.getElementById('kat');
    const seansSelect = document.getElementById('seans');
    if (katSelect && seansSelect) {
        katSelect.addEventListener('change', function() {
            if (katSelect.value === '80') {
                seansSelect.querySelector('option[value="3"]').style.display = 'none';
            } else {
                seansSelect.querySelector('option[value="3"]').style.display = 'block';
            }
        });
    }
});
