/* This file is part of Jeedom.
*
* Jeedom is free software: you can redistribute it and/or modify
* it under the terms of the GNU General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* Jeedom is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with Jeedom. If not, see <http://www.gnu.org/licenses/>.
*/
/*********************************************************************
* Affiche les informations du Token si le niveau de log du plugin est à debug
*********************************************************************/


/*********************************************************************
* Remplit le champs select avec la liste des enfants de l'équipement
*********************************************************************/
function getParameterByName(name, url = window.location.href) {
  // Cette fonction permet de récupérer la valeur d'un paramètre dans l'URL
  name = name.replace(/[\[\]]/g, '\\$&');
  const regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)');
  const results = regex.exec(url);
  if (!results) return null;
  if (!results[2]) return '';
  return decodeURIComponent(results[2].replace(/\+/g, ' '));
}

/**
 * Attend que le fichier JSON soit mis à jour avec les nouvelles données
 * Cette fonction essaie à intervalle régulier jusqu'à trouver les données mises à jour
 */
function waitForDataUpdate(eqLogicId, expectedEleve, maxAttempts = 60, delay = 1000) {
  let attempts = 0;
  $('#error-message').html('<i class="fas fa-hourglass-half fa-spin"></i> Mise à jour des données en cours...');

  function checkUpdate() {
    attempts++;
    $.ajax({
      type: "POST",
      url: "/plugins/ProJote/core/ajax/ProJote.ajax.php",
      data: { action: "GetConfig", eqlogic: eqLogicId },
      dataType: 'json',
      global: false,
      success: function (result) {
        if (result && result.state === 'ok' && result.result.Eleve === expectedEleve) {
          console.log('ProJote.js:: Données mises à jour avec le nouvel élève:', expectedEleve);
          setSyncSpinner(false);
          $('#error-message').empty();
          loadProJoteData(eqLogicId);
        } else if (attempts < maxAttempts) {
          setTimeout(checkUpdate, delay);
        } else {
          console.log('ProJote.js:: Délai maximum atteint, rechargement des données');
          setSyncSpinner(false);
          $('#error-message').empty();
          loadProJoteData(eqLogicId);
        }
      },
      error: function () {
        if (attempts < maxAttempts) {
          setTimeout(checkUpdate, delay);
        } else {
          setSyncSpinner(false);
          loadProJoteData(eqLogicId);
        }
      }
    });
  }

  checkUpdate();
}

function loadProJoteData(eqLogicId) {
  $('#error-message').empty();
  if (!eqLogicId) {
    $('#error-message').text('Erreur : ID de l\'équipement non trouvé.');
    $('.form-group.Token').hide();
    $('.form-group.Eleve').hide();
    return;
  }

  $.ajax({
    type: "POST",
    url: "/plugins/ProJote/core/ajax/ProJote.ajax.php",
    data: { action: "GetConfig", eqlogic: eqLogicId },
    dataType: 'json',
    global: false,
    success: function (result) {
      if (!result || result.state !== 'ok') {
        resetFields();
        return;
      }
      let data = result.result;

      // Afficher et remplir la section Eleve si des données existent
      if (data.Eleve && data.Eleve.trim() !== '') {
        $('#eleve-name').text(data.Eleve || '');
        $('#eleve-classe').text(data.Classe || '');
        $('#eleve-etablissement').text(data.Etablissement || '');
        $('.form-group.Eleve').show();
      } else {
        $('.form-group.Eleve').hide();
      }

      // Afficher Token si mode debug
      if (LogLevel === 'debug') {
        $('#Token_pronote_url').text(data.Token_pronote_url || '');
        $('.form-group.Token').show();
      } else {
        $('.form-group.Token').hide();
      }

      // Détecter compte parent via l'URL du token
      if (data.Token_pronote_url && data.Token_pronote_url.includes('parent.html')) {
        $('input[name="accountType"][value="parent"]').prop('checked', true);
        $('.form-group.listenfant').show();
        populateEnfantList(eqLogicId, data, function(selectedEnfant) {
          // Après un "Sauvegarder", Jeedom recharge la page avec saveSuccessFull=1
          // On profite du rechargement pour déclencher la synchro Pronote
          if (getParameterByName('saveSuccessFull') === '1' && selectedEnfant) {
            changeEnfant(eqLogicId, selectedEnfant);
          }
        });
      } else {
        $('input[name="accountType"][value="eleve"]').prop('checked', true);
        $('.form-group.listenfant').hide();
      }

      // Photo de profil
      let profilePicturePath = '/plugins/ProJote/data/' + eqLogicId + '/profile_picture.jpg';
      $.get(profilePicturePath)
        .done(function () {
          $('#local-picture').attr('src', profilePicturePath + '?' + new Date().getTime()).show();
        })
        .fail(function () {
          $('#local-picture').hide();
        });
    },
    error: function () {
      resetFields();
      $('.form-group.Token').hide();
      $('.form-group.Eleve').hide();
    }
  });
}

function setSyncSpinner(active) {
  if (active) {
    $('#bt_renameEqLogic_icon').addClass('hidden');
    $('#bt_renameEqLogic_spin').removeClass('hidden');
    $('#bt_renameEqLogic').prop('disabled', true);
  } else {
    $('#bt_renameEqLogic_spin').addClass('hidden');
    $('#bt_renameEqLogic_icon').removeClass('hidden');
    $('#bt_renameEqLogic').prop('disabled', false);
  }
}

function changeEnfant(eqLogicId, selectedEnfant) {
  if (!selectedEnfant || !eqLogicId) return;
  setSyncSpinner(true);
  $('#error-message').empty();
  $.ajax({
    type: "POST",
    url: "/plugins/ProJote/core/ajax/ProJote.ajax.php",
    data: { action: "ChangeEnfant", nomeleve: selectedEnfant, eqlogic: eqLogicId },
    dataType: 'json',
    global: false,
    error: function (request, status, error) {
      console.error("AJAX Error:", request, status, error);
      $('#error-message').text('Erreur lors du changement d\'élève. Vérifiez les logs.');
      setSyncSpinner(false);
    },
    success: function () {
      waitForDataUpdate(eqLogicId, selectedEnfant);
    }
  });
}

function resetFields() {
  $('#token-username').text('');
  $('#token-password').text('');
  $('#token-url').attr('href', '#').text('');
  $('#profile-picture').attr('src', '');
  $('#eleve-name').text('');
  $('#eleve-classe').text('');
  $('#eleve-etablissement').text('');
  $('#local-picture').attr('src', '').hide();
  $('#enfantlist').empty(); // Vider la liste des enfants
}

function populateEnfantList(eqLogicId, configData, callback) {
  console.log('ProJote.js:: populateEnfantList appelée avec eqLogicId:', eqLogicId);
  if ($('input[name="accountType"]:checked').val() !== 'parent') {
    return;
  }

  function fillList(data) {
    let listeRaw = data.Liste_Enfant || '[]';
    let enfants = [];
    try {
      enfants = typeof listeRaw === 'string' ? JSON.parse(listeRaw) : listeRaw;
    } catch (e) {
      console.error('ProJote.js:: Erreur parsing Liste_Enfant', e);
    }

    let $enfantList = $('#enfantlist');
    $enfantList.empty();
    let enfantActuel = data.Eleve || '';

    if (Array.isArray(enfants) && enfants.length > 0) {
      let found = false;
      enfants.forEach(function (enfant) {
        let enfantTrim = enfant.trim();
        $enfantList.append('<option value="' + htmlspecialchars(enfantTrim) + '">' + htmlspecialchars(enfantTrim) + '</option>');
        if (enfantTrim === enfantActuel) found = true;
      });
      if (found) {
        $enfantList.val(enfantActuel);
      } else if (enfants.length > 0) {
        $enfantList.val(enfants[0].trim());
      }
    } else {
      $enfantList.append('<option value="">Aucun enfant trouvé</option>');
    }

    if (callback) callback($enfantList.val());
  }

  if (configData) {
    fillList(configData);
  } else {
    $.ajax({
      type: "POST",
      url: "/plugins/ProJote/core/ajax/ProJote.ajax.php",
      data: { action: "GetConfig", eqlogic: eqLogicId },
      dataType: 'json',
      global: false,
      success: function (result) {
        if (result && result.state === 'ok') {
          fillList(result.result);
        }
      }
    });
  }
}

function htmlspecialchars(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

$(document).ready(function () {
  // attend que la page web (php) soit entiérement lu.
  // Masquer la liste des élèves par défaut
  $('.form-group.listenfant').hide();

  $('#bt_donProJote').on('click', function () {
    $('#modal_donProJote').modal('show');
  });

  // Ajouter un gestionnaire d'événements click pour les cartes d'équipement
  $('.eqLogicDisplayCard').on('click', function () {
    let eqLogicId = $(this).attr('data-eqlogic_id'); // Récupérer l'ID de l'équipement depuis l'attribut data
    console.log('ProJote.js:: Detection du click pour ', eqLogicId);
    loadProJoteData(eqLogicId);
    loadManualPhotoPreview(eqLogicId);
    //populateEnfantList(eqLogicId); // Appeler la fonction pour peupler la liste des enfants
  });

  // Vérifier si un équipement est déjà sélectionné lors du chargement de la page
  let eqLogicIdFromUrl = getParameterByName('id');
  if (eqLogicIdFromUrl) {
    console.log('ProJote.js:: Chargement des données pour ', eqLogicIdFromUrl);
    loadProJoteData(eqLogicIdFromUrl);
    loadManualPhotoPreview(eqLogicIdFromUrl);
    //populateEnfantList(eqLogicIdFromUrl); // Appeler la fonction pour peupler la liste des enfants
  }

  // Gestion de l'affichage du champ listenfant en fonction des radio buttons accountType
  $('input[name="accountType"]').change(function () {
    if ($(this).val() === 'parent') {
      $('.form-group.listenfant').show();
    } else {
      $('.form-group.listenfant').hide();
    }
  });
  // Trigger initial pour afficher/masquer selon la valeur par défaut
  $('input[name="accountType"]:checked').trigger('change');

  // Detection automatique parent dans l'URL lors de la saisie
  $('[data-l2key="url"]').on('input', function () {
    if ($(this).val().includes('parent.html')) {
      $('input[name="accountType"][value="parent"]').prop('checked', true).trigger('change');
    }
  });
});

/*********************************************************************
* Ajoutez un gestionnaire d'événements change pour le champ "AUTH"
*********************************************************************/

$('[data-l1key="configuration"][data-l2key="AUTH"]').on('change', function () {
  //Le but est d'afficher le bon menu en fonction de l'authentification choisit

  // Masque tous les divs
  $('.form-group.Login, .form-group.QRCode').hide();
  // Affiche le div correspondant à la valeur sélectionnée
  if ($(this).val() === 'Login') {
    $('.form-group.Login').show();
  } else if ($(this).val() === 'QRCode') {
    $('.form-group.QRCode').show();
  }
});
// Trigger le changement pour afficher le div correspondant à la valeur par défaut
$('[data-l1key="configuration"][data-l2key="AUTH"]').trigger('change');

/*****************************************************
 * Gestion de l'affichage du champ listenfant
 *****************************************************/
// Applique l'enfant sélectionné et synchronise avec Pronote
$('#bt_renameEqLogic').on('click', function () {
  let eqLogicId = $('.eqLogicAttr[data-l1key=id]').val();
  let selectedEnfant = $('#enfantlist').val();
  changeEnfant(eqLogicId, selectedEnfant);
});

/*******************************************************
* Ajout de l'événement de clic sur le bouton Valider
*******************************************************/
$('#bt_Validate').on('click', function () {
  // Récupération des données
  // Récupérer les valeurs des éléments
  let Url = document.querySelector('[data-l2key="url"]').value;
  let Login = document.querySelector('[data-l2key="login"]').value;
  let Password = document.querySelector('[data-l2key="password"]').value;
  let CasEnt = document.querySelector('[data-l2key="CasEnt"]').value;
  let selectedEnfant = document.querySelector('[data-l2key="enfant"]').value;
  // Afficher le sablier
  document.querySelector('.form-group.Login .fa-hourglass-half').classList.remove('hidden');
  document.querySelector('.form-group.Login .fa-check').classList.add('hidden');
  document.querySelector('.form-group.Login .fa-times').classList.add('hidden');


  //on valide si Url contient la chaine de caractéres parent.html si oui il faut cocher la case type="checkbox" id="Parent"
  if (Url.includes('parent.html')) {
    console.log('ProJote.js:: URL contient parent.html');
    // Si l'URL contient "parent.html", sélectionnez le radio "Parent"
    $('input[name="accountType"][value="parent"]').prop('checked', true);
    // Affiche le form-group listenfant
    $('.form-group.listenfant').show();
  }
  // Exécution de la requête AJAX
  $.ajax({
    type: "POST", // Méthode de transmission des données au fichier php
    url: "/plugins/ProJote/core/ajax/ProJote.ajax.php", // URL du script PHP AJAX

    data: {
      action: "Validate", // Action à exécuter dans le script PHP
      url: Url,
      login: Login,
      password: Password,
      ent: CasEnt,
      nomeleve: selectedEnfant,
      eqlogic: $('.eqLogicAttr[data-l1key=id]').val(),
    },

    dataType: 'json',
    global: false,
    error: function (request, status, error) {
      // Gestion des erreurs
      console.error("AJAX Error:", request, status, error);
    },
    success: function (data) {
      // Traitement de la réponse JSON
      console.log("AJAX Success:", data);

      if (data.state === 'ok') {
        // Si la réponse est True
        // Masquer le sablier et afficher la coche
        document.querySelector('.form-group.Login .fa-hourglass-half').classList.add('hidden');
        document.querySelector('.form-group.Login .fa-check').classList.remove('hidden');
        //je fais disparataire la coche au bout de 10 secondes
        setTimeout(function () {
          document.querySelector('.form-group.Login .fa-check').classList.add('hidden');
        }, 10000); // 10000 millisecondes = 10 secondes
        let eqLogicIdFromUrl = getParameterByName('id');
        if (eqLogicIdFromUrl) {
          console.log('ProJote.js:: Chargement des données pour ', eqLogicIdFromUrl);
          loadProJoteData(eqLogicIdFromUrl);
        }
      } else {
        // Masquer le sablier et afficher la croix
        document.querySelector('.form-group.Login .fa-hourglass-half').classList.add('hidden');
        document.querySelector('.form-group.Login .fa-times').classList.remove('hidden');
        //je fais disparataire la coche au bout de 10 secondes
        setTimeout(function () {
          document.querySelector('.form-group.Login .fa-times').classList.add('hidden');
        }, 10000); // 10000 millisecondes = 10 secondes
      }
    }
  });
});


/**************************************
 * Tratement de la réception du QR CODE
 ***************************************/
// Les function suivante gére le copier selectionner ou "drop" de l'image QRCODE
document.querySelector('.rectangle').addEventListener('paste', function (e) {
  let { items } = e.clipboardData;
  for (let i = 0; i < items.length; i++) {
    if (items[i].type.indexOf('image') !== -1) {
      let blob = items[i].getAsFile();
      let reader = new FileReader();
      reader.onload = function (event) {
        let imageData = event.target.result;
        handleImage(imageData);
      };
      reader.readAsDataURL(blob);
    }
  }
});
document.getElementById('fileInput').addEventListener('change', function (e) {
  let file = e.target.files[0];
  let reader = new FileReader();
  reader.onload = function (event) {
    let imageData = event.target.result;
    handleImage(imageData);
  };
  reader.readAsDataURL(file);
});
document.querySelector('.rectangle').addEventListener('drop', function (e) {
  e.preventDefault();
  e.stopPropagation();
  let file = e.dataTransfer.files[0];
  let reader = new FileReader();
  reader.onload = function (event) {
    let imageData = event.target.result;
    handleImage(imageData);
  };
  reader.readAsDataURL(file);
});

function sendImageToServer(code, pin) {
  // Fonction for send QRcode data to AJAX and python script
  document.querySelector('.form-group.QRCode .fa-hourglass-half').classList.remove('hidden');
  $.ajax({
    type: "POST",
    url: "/plugins/ProJote/core/ajax/ProJote.ajax.php",
    data: {
      action: "ValidateQRCode",
      QRinfo: code,
      pin: pin,
      eqlogic: $('.eqLogicAttr[data-l1key=id]').val(),
    },
    dataType: 'json',
    global: false,
    error: function (request, status, error) {
      console.error("AJAX Error:", error);
      document.querySelector('.form-group.QRCode .fa-hourglass-half').classList.add('hidden');
      document.querySelector('.form-group.QRCode .fa-times').classList.remove('hidden');
      document.getElementById('error-message').textContent = 'Une erreur s\'est produite lors de la validation du code QR.';
      document.getElementById('error-message').style.color = 'red';
    },
    success: function (data) {
      document.querySelector('.form-group.QRCode .fa-hourglass-half').classList.add('hidden');
      if (data.state === 'ok') {
        document.querySelector('.form-group.QRCode .fa-hourglass-half').classList.add('hidden');
        document.querySelector('.form-group.QRCode .fa-check').classList.remove('hidden');
        //je fais disparataire la coche au bout de 10 secondes
        setTimeout(function () {
          document.querySelector('.form-group.QRCode .fa-check').classList.add('hidden');
        }, 10000); // 10000 millisecondes = 10 secondes
        let eqLogicIdFromUrl = getParameterByName('id');
        if (eqLogicIdFromUrl) {
          console.log('ProJote.js:: Chargement des données pour ', eqLogicIdFromUrl);
          loadProJoteData(eqLogicIdFromUrl);
        }
      } else {
        console.error(data.result);
        document.getElementById('error-message').textContent = data.result;
        document.getElementById('error-message').style.color = 'red';
        document.querySelector('.form-group.QRCode .fa-hourglass-half').classList.add('hidden');
        document.querySelector('.form-group.QRCode .fa-times').classList.remove('hidden');
        //je fais disparataire la coche au bout de 10 secondes
        setTimeout(function () {
          document.querySelector('.form-group.QRCode .fa-times').classList.add('hidden');
        }, 10000); // 10000 millisecondes = 10 secondes
      }
      // Exécuter la fonction saveEqLogic après la validation du QR code
      /*       if (typeof saveEqLogic === 'function') {
              saveEqLogic();
            } else {
              console.error("La fonction saveEqLogic n'est pas définie. Vérifier dans la fichier PHP que la fonction plugin tempalte est bien incluse");
            } */
    }
  });
}

function resizeImage(imageData, width, height) {
  return new Promise((resolve, reject) => {
    let img = new Image();
    img.onload = function () {
      let canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      let ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, width, height);
      let resizedImageData = canvas.toDataURL('image/png');
      resolve(resizedImageData);
    };
    img.onerror = function () {
      reject(new Error('Failed to load image'));
    };
    img.src = imageData;
  });
}

function displayImage(imageData) {
  let img = document.createElement('img');
  img.src = imageData;
  img.style.border = '5px solid #90EE90'; // Couleur du cadre en vert clair
  let rectangle = document.querySelector('.rectangle');
  if (rectangle) {
    rectangle.innerHTML = '';
    // Créez un élément div pour contenir l'image et le texte
    let container = document.createElement('div');
    container.style.position = 'relative';
    rectangle.appendChild(container);
    // Ajoutez l'image à l'élément div
    container.appendChild(img);
    // Ajoutez ce gestionnaire d'événements pour afficher une fenêtre de demande de code PIN
    img.addEventListener('click', function () {
      let pin = prompt('Veuillez entrer votre code PIN de 4 chiffres :');
      // Vérifiez le code PIN ici
      let pinRegex = /^\d{4}$/;
      if (pinRegex.test(pin)) {
        // Le code PIN est valide
        console.log('Code PIN valide :', pin);
      } else {
        // Le code PIN est invalide
        alert('Code PIN invalide. Veuillez entrer un code PIN de 4 chiffres.');
      }
    });
  } else {
    console.error('Element with class "rectangle" not found');
  }
}

function handleImage(imageData) {
  resizeImage(imageData, 200, 200).then(function (resizedImageData) {
    let img = new Image();
    img.onload = function () {
      // Décoder le code QR à partir de l'image
      let canvas = document.createElement('canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      let ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);
      let imageData = ctx.getImageData(0, 0, img.width, img.height);
      let code = jsQR(imageData.data, imageData.width, imageData.height);
      // Si le code QR est décodé avec succès, afficher les données
      if (code) {
        console.log('Données du QR code :', code.data);
        // Demande le code PIN à l'utilisateur uniquement si le QR est valide
        let pin = prompt('Veuillez entrer votre code PIN de 4 chiffres :');
        let pinRegex = /^\d{4}$/;
        if (pinRegex.test(pin)) {
          sendImageToServer(code.data, pin);
        } else {
          alert('Code PIN invalide. Veuillez entrer un code PIN de 4 chiffres.');
        }
      } else {
        console.log('Impossible de décoder le code QR');
        $('#error-message').text('Erreur : Impossible de décoder le QRcode ');
      }
      displayImage(resizedImageData);
    };
    img.onerror = function () {
      alert('Erreur lors du chargement de l\'image.');
      document.querySelector('.rectangle').innerHTML = '';
    };
    img.src = resizedImageData;
  });
}

/********************************************************* 
*Permet la réorganisation des commandes dans l'équipement 
**********************************************************/
$("#table_cmd").sortable({
  axis: "y",
  cursor: "move",
  items: ".cmd",
  placeholder: "ui-state-highlight",
  tolerance: "intersect",
  forcePlaceholderSize: true
})

/* function prePrintEqLogic(_eqlogicId) {
  document.getElementById('div_pageContainer')?.querySelector('.eqLogicAttr[data-l1key="configuration"][data-l2key="enfant"]').jeeValue(0)
} */

/***************************************************************
 *  Fonction pour trier les lignes de la table par ID croissant
 **************************************************************/
function sortTableById(_cmd) {
  let table = document.getElementById('table_cmd').getElementsByTagName('tbody')[0];
  let rows = table.getElementsByTagName('tr');
  let sortedRows = Array.from(rows).sort((a, b) => {
    let idA = parseInt(a.getAttribute('data-cmd_id'));
    let idB = parseInt(b.getAttribute('data-cmd_id'));
    return idA - idB;
  });
  // Supprimer les lignes existantes de la table
  while (table.firstChild) {
    table.removeChild(table.firstChild);
  }
  // Ajouter les lignes triées à la table
  sortedRows.forEach(row => {
    table.appendChild(row);
  });
}
/* ****************************************************************
*Fonction permettant l'affichage des commandes dans l'équipement 
******************************************************************=*/
function addCmdToTable(_cmd) {
  if (!isset(_cmd)) {
    _cmd = { configuration: {} }   // affectation directe (pas let/var) pour que le paramètre soit réassigné
  }
  if (!isset(_cmd.configuration)) {
    _cmd.configuration = {}
  }
  sortTableById();
  let tr = '<tr class="cmd" data-cmd_id="' + init(_cmd.id) + '">'

  // ── Colonne ID ────────────────────────────────────────────────
  tr += '<td>'
  tr += '<span class="cmdAttr" data-l1key="id"></span>'
  tr += '</td>'

  // ── Colonne Commande (nom + icône) ────────────────────────────
  tr += '<td>'
  tr += '<div class="input-group">'
  tr += '<input class="cmdAttr form-control input-sm roundedLeft" data-l1key="name" placeholder="{{Nom de la commande}}">'
  tr += '<span class="input-group-btn"><a class="cmdAction btn btn-sm btn-default" data-l1key="chooseIcon" title="{{Choisir une icône}}"><i class="fas fa-icons"></i></a></span>'
  tr += '<span class="cmdAttr input-group-addon roundedRight" data-l1key="display" data-l2key="icon" style="font-size:19px;padding:0 5px 0 0!important;"></span>'
  tr += '</div>'
  // Champ caché pour la commande info liée (requis par le core Jeedom)
  tr += '<select class="cmdAttr form-control input-sm" data-l1key="value" style="display:none;margin-top:5px;" title="{{Commande info liée}}">'
  tr += '<option value="">{{Aucune}}</option>'
  tr += '</select>'
  tr += '</td>'

  // ── Colonne Valeur ────────────────────────────────────────────
  tr += '<td style="vertical-align:middle;">'
  if (_cmd.type === 'info') {
    tr += '<span class="cmdAttr pjw-hs-raw" data-l1key="htmlstate" style="display:none;"></span>'
    tr += '<span class="pjw-val-display" style="display:block;word-break:break-all;font-size:11px;opacity:.7;"></span>'
  }
  tr += '</td>'

  // ── Colonne Options ───────────────────────────────────────────
  // Afficher (isVisible) : pour toutes les commandes — contrôle
  //   l'affichage de la commande sur le dashboard Jeedom.
  // Historiser (isHistorized) : uniquement pour les commandes
  //   de type "numeric" — enregistre l'historique des valeurs.
  tr += '<td style="white-space:nowrap;vertical-align:middle;">'
  tr += '<label class="checkbox-inline" style="font-size:12px;">'
  tr += '<input type="checkbox" class="cmdAttr" data-l1key="isVisible"/> {{Afficher}}'
  tr += '</label>'
  if (_cmd.subType === 'numeric') {
    tr += '<br><label class="checkbox-inline" style="font-size:12px;">'
    tr += '<input type="checkbox" class="cmdAttr" data-l1key="isHistorized"/> {{Historiser}}'
    tr += '</label>'
  }
  tr += '</td>'

  // ── Colonne Actions ───────────────────────────────────────────
  // Configurer (⚙) : toujours disponible si la commande existe en BDD.
  // Tester : uniquement pour les commandes de type "action".
  // Supprimer (🚫) : toujours à droite, aligné en colonne.
  tr += '<td style="white-space:nowrap;vertical-align:middle;">'
  tr += '<div style="display:flex;align-items:center;justify-content:flex-end;gap:4px;">'
  if (is_numeric(_cmd.id)) {
    tr += '<a class="btn btn-default btn-xs cmdAction" data-action="configure" title="{{Configuration avancée}}"><i class="fas fa-cogs"></i></a>'
    if (_cmd.type === 'action') {
      tr += '<a class="btn btn-default btn-xs cmdAction" data-action="test" title="{{Tester}}"><i class="fas fa-rss"></i></a>'
    }
  }
  tr += '<i class="fas fa-minus-circle cmdAction cursor" data-action="remove" title="{{Supprimer}}" style="color:#e74c3c;font-size:16px;"></i>'
  tr += '</div>'
  tr += '</td>'

  tr += '</tr>'
  $('#table_cmd tbody').append(tr)
  let Ntr = $('#table_cmd tbody tr').last()
  jeedom.eqLogic.buildSelectCmd({
    id: $('.eqLogicAttr[data-l1key=id]').val(),
    filter: { type: 'info' },
    error: function (error) {
      $('#div_alert').showAlert({ message: error.message, level: 'danger' })
    },
    success: function (result) {
      Ntr.find('.cmdAttr[data-l1key=value]').append(result)
      Ntr.setValues(_cmd, '.cmdAttr')
      jeedom.cmd.changeType(Ntr, init(_cmd.subType))
      if (_cmd.type === 'info') {
        const hsRaw = Ntr.find('.pjw-hs-raw')[0]
        if (hsRaw && hsRaw.innerHTML) {
          const _tmp = document.createElement('div')
          _tmp.innerHTML = hsRaw.innerHTML
          const stateSpan = _tmp.querySelector('.cmdTableState')
          if (stateSpan) {
            const txt = (stateSpan.textContent || stateSpan.innerText || '').trim()
            let display = txt || '—'
            if (txt) {
              try {
                const parsed = JSON.parse(txt)
                if (Array.isArray(parsed)) {
                  display = parsed.length > 0 ? '[' + parsed.length + ' élément(s)]' : '[ vide ]'
                } else if (typeof parsed === 'object' && parsed !== null) {
                  const keys = Object.keys(parsed)
                  display = '{' + keys.slice(0, 3).join(', ') + (keys.length > 3 ? ', …' : '') + '}'
                }
              } catch (e) {
                if (txt.startsWith('[')) display = '[ … ]'
                else if (txt.startsWith('{')) display = '{ … }'
                else display = txt.length > 60 ? txt.substring(0, 60) + '…' : txt
              }
            }
            Ntr.find('.pjw-val-display').text(display).attr('title', txt)
          }
        }
      }
    }
  })
}

/*******************************************************************************
 * ONGLET AFFICHAGE — Prévisualisation du widget
 ******************************************************************************/

/**
 * Charge le rendu live du widget ProJote dans la zone de prévisualisation (#pjw-preview-zone).
 *
 * Appelle eqLogic.ajax.php?action=toHtml pour obtenir le HTML généré par ProJote::toHtml().
 * La réponse a la forme : { state:'ok', result:{ html:'...', id:..., type:... } }
 * Les scripts inline du widget (IIFE) sont exécutés via $.globalEval().
 *
 * Appelé : à l'ouverture de l'onglet Affichage (shown.bs.tab) et sur clic du bouton Rafraîchir.
 */
function refreshProJotePreview() {
  let id = $('.eqLogicAttr[data-l1key=id]').val() || getParameterByName('id');
  let $zone = $('#pjw-preview-zone');
  if (!id) {
    $zone.html('<span class="text-muted" style="font-size:12px;">Sélectionnez un équipement pour prévisualiser.</span>');
    return;
  }
  $zone.css({ 'align-items': 'center', 'justify-content': 'center' })
       .html('<i class="fas fa-spinner fa-spin"></i>');

  $.ajax({
    type: 'POST',
    url: 'core/ajax/eqLogic.ajax.php',
    data: { action: 'toHtml', id: id, version: 'dashboard' },
    dataType: 'json',
    success: function (data) {
      // La réponse de eqLogic.ajax.php?action=toHtml est : { state:'ok', result:{ html:'...', id:..., ... } }
      let html = data && data.state === 'ok' && data.result && data.result.html ? data.result.html : null;
      if (html) {
        $zone.css({ 'align-items': 'flex-start', 'justify-content': 'flex-start' }).empty();
        let $wrap = $('<div>').html(html);
        // Extraire les scripts AVANT injection (les retirer du HTML)
        let scripts = [];
        $wrap.find('script').each(function () {
          scripts.push($(this).text());
          $(this).remove();
        });
        // 1. Injecter le HTML dans le DOM (les éléments existent maintenant)
        $zone.append($wrap.children());
        // 2. Exécuter les scripts APRÈS injection — render(D,...) trouve bien les éléments
        scripts.forEach(function (code) {
          try { $.globalEval(code); } catch (e) { console.warn('ProJote preview script:', e); }
        });
      } else {
        $zone.css({ 'align-items': 'center', 'justify-content': 'center' })
             .html('<span class="text-warning" style="font-size:12px;">Sauvegardez l\'équipement avant de prévisualiser.</span>');
      }
    },
    error: function () {
      $zone.css({ 'align-items': 'center', 'justify-content': 'center' })
           .html('<span class="text-danger" style="font-size:12px;">Erreur lors du chargement de la prévisualisation.</span>');
    }
  });
}

// Nettoyage des handlers ProJote pour éviter les doublons lors des rechargements AJAX Jeedom.
// ProJote.js est ré-évalué à chaque navigation AJAX vers la page de config ; sans ce .off(),
// chaque $(document).on() s'accumule et déclenche l'événement N fois.
$(document).off('.projote');

// Rafraîchissement auto à l'ouverture de l'onglet Affichage
$(document).on('shown.bs.tab.projote', 'a[href="#eqlogicDisplaytab"]', function () {
  refreshProJotePreview();
});

// Bouton Rafraîchir
$(document).on('click.projote', '#pjw-preview-refresh', function () {
  refreshProJotePreview();
});

/*******************************************************************************
 * ONGLET AFFICHAGE — Photo de profil manuelle
 ******************************************************************************/

/**
 * Charge les miniatures de photo dans l'onglet Affichage pour un équipement donné.
 *
 * Teste l'existence des deux fichiers via GET HTTP :
 *   - /plugins/ProJote/data/{id}/profile_picture.jpg      → photo Pronote (démon)
 *   - /plugins/ProJote/data/{id}/profile_picture_manual.jpg → photo manuelle (upload)
 *
 * Affiche ou masque les blocs #pjw-pronote-photo-wrap / #pjw-manual-photo-wrap en conséquence.
 * Un timestamp est ajouté à l'URL pour contourner le cache navigateur.
 *
 * @param {string|number} eqLogicId  ID de l'équipement ProJote.
 */
function loadManualPhotoPreview(eqLogicId) {
  if (!eqLogicId) return;
  let ts = '?_=' + Date.now();

  // Photo Pronote (téléchargée par le démon)
  let pronotePath = '/plugins/ProJote/data/' + eqLogicId + '/profile_picture.jpg';
  $.get(pronotePath + ts)
    .done(function () {
      $('#pjw-pronote-photo-img').attr('src', pronotePath + ts);
      $('#pjw-pronote-photo-wrap').show();
      $('#pjw-no-pronote-photo').hide();
    })
    .fail(function () {
      $('#pjw-pronote-photo-wrap').hide();
      $('#pjw-no-pronote-photo').show();
    });

  // Photo manuelle (uploadée par l'utilisateur)
  let manualPath = '/plugins/ProJote/data/' + eqLogicId + '/profile_picture_manual.jpg';
  $.get(manualPath + ts)
    .done(function () {
      $('#pjw-manual-photo-img').attr('src', manualPath + ts);
      $('#pjw-manual-photo-wrap').show();
      $('#pjw-no-manual-photo').hide();
    })
    .fail(function () {
      $('#pjw-manual-photo-wrap').hide();
      $('#pjw-no-manual-photo').show();
    });
}

// Upload d'une nouvelle photo manuelle
$(document).on('change.projote', '#pjw-manual-photo-input', function () {
  let file = this.files[0];
  if (!file) return;
  let eqLogicId = $('.eqLogicAttr[data-l1key=id]').val();
  if (!eqLogicId) {
    $('#pjw-manual-photo-status').text('Sauvegardez l\'équipement avant d\'uploader une photo.').css('color', 'red');
    return;
  }

  let formData = new FormData();
  formData.append('action', 'UploadManualPhoto');
  formData.append('eqlogic', eqLogicId);
  formData.append('photo', file);

  $('#pjw-manual-photo-status').html('<i class="fas fa-spinner fa-spin"></i> Envoi en cours…').css('color', '');

  $.ajax({
    type: 'POST',
    url: '/plugins/ProJote/core/ajax/ProJote.ajax.php',
    data: formData,
    contentType: false,
    processData: false,
    dataType: 'json',
    success: function (data) {
      if (data && data.state === 'ok') {
        let ts = '?_=' + Date.now();
        let manualPath = '/plugins/ProJote/data/' + eqLogicId + '/profile_picture_manual.jpg';
        $('#pjw-manual-photo-img').attr('src', manualPath + ts);
        $('#pjw-manual-photo-wrap').show();
        $('#pjw-no-manual-photo').hide();
        $('#pjw-manual-photo-status').text('Photo enregistrée.').css('color', 'green');
        setTimeout(function () { $('#pjw-manual-photo-status').text(''); }, 3000);
      } else {
        $('#pjw-manual-photo-status').text('Erreur : ' + (data ? data.result : 'inconnue')).css('color', 'red');
      }
    },
    error: function () {
      $('#pjw-manual-photo-status').text('Erreur lors de l\'envoi.').css('color', 'red');
    }
  });
});

// Suppression de la photo manuelle (bouton ✕ en overlay sur la miniature)
$(document).on('click.projote', '#pjw-manual-photo-delete', function () {
  let eqLogicId = $('.eqLogicAttr[data-l1key=id]').val();
  if (!eqLogicId) return;
  if (!confirm('Supprimer la photo manuelle ?')) return;

  $.ajax({
    type: 'POST',
    url: '/plugins/ProJote/core/ajax/ProJote.ajax.php',
    data: { action: 'DeleteManualPhoto', eqlogic: eqLogicId },
    dataType: 'json',
    success: function (data) {
      if (data && data.state === 'ok') {
        $('#pjw-manual-photo-wrap').hide();
        $('#pjw-no-manual-photo').show();
        $('#pjw-manual-photo-img').attr('src', '');
        $('#pjw-manual-photo-status').text('Photo supprimée.').css('color', 'green');
        setTimeout(function () { $('#pjw-manual-photo-status').text(''); }, 3000);
      }
    }
  });
});

