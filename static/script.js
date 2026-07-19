// static/script.js

function formatInputCLP(input) {
    var value = input.value.replace(/\D/g, "");
    if(value === "") { input.value = ""; return; }
    input.value = new Intl.NumberFormat('es-CL').format(value);
}

function modificarMonto(cambio) {
    var campo = document.getElementById('monto_inicial');
    var valorActual = parseInt(campo.value.replace(/\./g, "")) || 0;
    var nuevoValor = valorActual + cambio;
    if (nuevoValor < 0) nuevoValor = 0;
    campo.value = nuevoValor;
    formatInputCLP(campo);
}

function modificarNumero(idCampo, cambio, esDecimal = false) {
    var campo = document.getElementById(idCampo);
    var valorActual = parseFloat(campo.value);
    if (isNaN(valorActual)) valorActual = 0;
    var nuevoValor = valorActual + cambio;
    if (nuevoValor < 0) nuevoValor = 0;
    if (esDecimal) {
        campo.value = parseFloat(nuevoValor.toFixed(2));
    } else {
        campo.value = Math.round(nuevoValor);
    }
}

function abrirModal() {
    var modal = document.getElementById('modalDesglose');
    if(modal) modal.style.display = 'flex';
}

function cerrarModal() {
    var modal = document.getElementById('modalDesglose');
    if(modal) modal.style.display = 'none';
}

// Cerrar al hacer clic fuera del modal
window.onclick = function(event) {
    var modal = document.getElementById('modalDesglose');
    if (event.target == modal) {
        modal.style.display = 'none';
    }
}

// Formatear al cargar la página si ya hay un valor
window.addEventListener('DOMContentLoaded', function() {
    var campoMonto = document.getElementById('monto_inicial');
    if(campoMonto && campoMonto.value !== "") {
        formatInputCLP(campoMonto);
    }
});