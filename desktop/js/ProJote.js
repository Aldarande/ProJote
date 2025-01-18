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
* Remplit le champs select avec la liste des enfants de l'équipement
*********************************************************************/
function getParameterByName(name, url) {
  if (!url) url = window.location.href;
  name = name.replace(/[\[\]]/g, '\\$&');
  var regex = new RegExp('[?&]' + name + '(=([^&#]*)|&|#|$)'),
    results = regex.exec(url);
  if (!results) return null;
  if (!results[2]) return '';
  return decodeURIComponent(results[2].replace(/\+/g, ' '));
}

// Gestion de l'affichage du champ listenfant en fonction de la case à cocher Parent
$('#Parent').change(function () {
  if ($(this).is(':checked')) {
    $('.form-group.listenfant').show(); // Affiche la liste des enfants
    populateEnfantList(); // Met à jour la liste si nécessaire
  } else {
    $('.form-group.listenfant').hide(); // Cache la liste des enfants
    $('#enfantList').empty(); // Vide la liste des enfants
  }
});

// Initialiser l'état du champ listenfant au chargement de la page
if ($('#Parent').is(':checked')) {
  $('.form-group.listenfant').show(); // Affiche la liste au démarrage si Parent est coché
  populateEnfantList(); // Remplit la liste si nécessaire
} else {
  $('.form-group.listenfant').hide(); // Cache la liste au démarrage
  $('#enfantList').empty(); // Vide la liste au démarrage
}

function loadProJoteData(eqLogicId) {
  if (eqLogicId) {
    var filePath = '/plugins/ProJote/data/' + eqLogicId + '/enfant.ProJote.json.txt';
    var profilePicturePath = '/plugins/ProJote/data/' + eqLogicId + '/profile_picture.jpg';
    console.log('ProJote.js:: emplacement du Fichier ' + filePath);
    // Vérifier la présence du fichier avant de tenter de récupérer les données
    $.get(filePath)
      .done(function () {
        // Le fichier existe, continuer à récupérer les données
        $.getJSON(filePath, function (data) {
          console.log('ProJote.js:: données récupérées', data);
          if (data) {
            var token = data.Token || null;
            if (token) {
              var tokenUrl = token.pronote_url ? $('<div>').text(token.pronote_url).html() : 'Non défini';
              var tokenUsername = token.username ? $('<div>').text(token.username).html() : 'Non défini';
              var tokenPassword = token.password ? $('<div>').text(token.password).html() : 'Non défini';
              var tokenClientIdentifier = token.client_identifier ? $('<div>').text(token.client_identifier).html() : 'Non défini';
              var tokenUuid = token.uuid ? $('<div>').text(token.uuid).html() : 'Non défini';

              $('#token-url').attr('href', tokenUrl).text(tokenUrl);
              $('#token-username').text(tokenUsername);
              $('#token-password').text(tokenPassword);
              $('#token-client-identifier').text(tokenClientIdentifier);
              $('#token-uuid').text(tokenUuid);
              //$('.form-group.Token').show(); // Afficher la section TOKEN
            } else {
              $('#error-message').text('Erreur : Les informations de Token sont absentes.');
              resetFields();
            }

            // Afficher les informations de l'élève
            var eleve = data.Eleve || 'Inconnu';
            var classe = data.Classe || 'Inconnue';
            var etablissement = data.Etablissement || 'Inconnu';
            var localPicture = data.Local_Picture ? data.Local_Picture.replace('/var/www/html', '') : '';

            $('#eleve-name').text(eleve);
            $('#eleve-classe').text(classe);
            $('#eleve-etablissement').text(etablissement);

            if (localPicture) {
              $('#local-picture').attr('src', localPicture).show();
            } else {
              $('#local-picture').hide();
            }

            $('.form-group.Eleve').show(); // Afficher la section Elève
          } else {
            $('#error-message').text('Erreur : Le fichier JSON est invalide.');
            resetFields();
          }
        }).fail(function (jqXHR, textStatus, errorThrown) {
          console.log('ProJote.js:: erreur lors de la récupération du fichier JSON', textStatus, errorThrown);
          $('#error-message').text('Erreur : Le fichier n\'existe pas à l\'emplacement spécifié.');
          resetFields();
        });

        $.get(profilePicturePath)
          .done(function () {
            console.log('ProJote.js:: image profile_picture.jpg récupérée avec succès');
            $('#profile-picture').attr('src', profilePicturePath);
          })
          .fail(function (jqXHR, textStatus, errorThrown) {
            console.log('ProJote.js:: erreur lors de la récupération de l\'image', textStatus, errorThrown);
            $('#error-message').append('<p>Le fichier profile_picture.jpg n\'existe pas.</p>');
            $('#profile-picture').attr('src', ''); // Réinitialiser l'image
          });

        populateEnfantList(eqLogicId); // Appeler la fonction pour peupler la liste des enfants
      })
      .fail(function () {
        // Le fichier n'existe pas, afficher un message d'erreur et réinitialiser les champs
        $('#error-message').text('Erreur : Le fichier enfant.ProJote.json.txt n\'existe pas.');
        resetFields();
        $('.form-group.Token').hide(); // Masquer la section TOKEN
        $('.form-group.Eleve').hide(); // Masquer la section Elève
      });
  } else {
    $('#error-message').text('Erreur : ID de l\'équipement non trouvé.');
    resetFields();
    $('.form-group.Token').hide(); // Masquer la section TOKEN
    $('.form-group.Eleve').hide(); // Masquer la section Elève
  }
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
  $('#enfantList').empty(); // Vider la liste des enfants
}

function populateEnfantList(eqLogicId) {
  if (!$('.form-group.listenfant').is(':visible')) {
    console.log('ProJote.js:: Liste des enfants non affichée, aucune action.');
    return;
  }

  var filePath = '/plugins/ProJote/data/' + eqLogicId + '/enfant.ProJote.json.txt';
  $.getJSON(filePath, function (data) {
    if (data && data.Liste_Enfant) {
      var enfants = JSON.parse(data.Liste_Enfant); // Transformer la chaîne en tableau
      var $enfantList = $('#enfantList');
      $enfantList.empty(); // Vider la liste existante

      if (Array.isArray(enfants)) {
        enfants.forEach(function (enfant) {
          $enfantList.append('<option value="' + htmlspecialchars(enfant.trim()) + '">' + htmlspecialchars(enfant.trim()) + '</option>');
        });
      } else {
        $enfantList.append('<option value="">Aucun enfant trouvé</option>');
      }
    } else {
      $('#error-message').text('Erreur : Liste_Enfant non trouvée ou fichier JSON invalide');
      $('#enfantList').empty();
    }
  }).fail(function (jqXHR, textStatus, errorThrown) {
    console.log('ProJote.js:: erreur lors de la récupération de la liste des enfants', textStatus, errorThrown);
    $('#error-message').text('Erreur : Le fichier n\'existe pas à l\'emplacement spécifié.');
    $('#enfantList').empty();
  });
}


function htmlspecialchars(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

$(document).ready(function () {
  // Ajouter un gestionnaire d'événements click pour les cartes d'équipement
  $('.eqLogicDisplayCard').on('click', function () {
    var eqLogicId = $(this).attr('data-eqlogic_id'); // Récupérer l'ID de l'équipement depuis l'attribut data
    console.log('ProJote.js:: Detection du click pour ', eqLogicId);
    loadProJoteData(eqLogicId);
    populateEnfantList(eqLogicId); // Appeler la fonction pour peupler la liste des enfants
  });

  // Vérifier si un équipement est déjà sélectionné lors du chargement de la page
  var eqLogicIdFromUrl = getParameterByName('id');
  if (eqLogicIdFromUrl) {
    console.log('ProJote.js:: Chargement des données pour ', eqLogicIdFromUrl);
    loadProJoteData(eqLogicIdFromUrl);
    populateEnfantList(eqLogicIdFromUrl); // Appeler la fonction pour peupler la liste des enfants
  }

  // Gestion de l'affichage du champ listenfant en fonction de la case à cocher Parent
  $('#Parent').change(function () {
    if ($(this).is(':checked')) {
      $('.form-group.listenfant').show();
    } else {
      $('.form-group.listenfant').hide();
    }
  });

  // Initialiser l'état du champ listenfant en fonction de la case à cocher Parent
  if ($('#Parent').is(':checked')) {
    $('.form-group.listenfant').show();
  } else {
    $('.form-group.listenfant').hide();
  }
});
/*********************************************************************
* Ajoutez un gestionnaire d'événements change pour le champ "AUTH"
*********************************************************************/

$('[data-l1key="configuration"][data-l2key="AUTH"]').on('change', function () {
  // Récupère la valeur sélectionnée
  var selectedAuth = $(this).val();
  // Masque tous les divs
  $('.form-group.Login, .form-group.QRCode').hide();
  // Affiche le div correspondant à la valeur sélectionnée
  if (selectedAuth === 'Login') {
    $('.form-group.Login').show();
  } else if (selectedAuth === 'QRCode') {
    $('.form-group.QRCode').show();
  }
});
// Trigger le changement pour afficher le div correspondant à la valeur par défaut
$('[data-l1key="configuration"][data-l2key="AUTH"]').trigger('change');


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
  let NomEleve = document.querySelector('[data-l2key="enfant"]').value;


  // Transformer en un tableau d'objets

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
      nomeleve: NomEleve, //|| "Inconnu"
      eqlogic: $('.eqLogicAttr[data-l1key=id]').value(),
    },

    dataType: 'json',
    global: false,
    error: function (request, status, error) {
      // Gestion des erreurs
      console.error("AJAX Error:", request, status, error);
      $('#bt_Validate').next('.fa-check-circle').remove();
      // Affichage de la croix rouge à droite du bouton
      $('#bt_Validate').after('<i class="fas fa-times" style="color:red;margin-left:5px;"></i>');
    },
    success: function (data) {
      // Traitement de la réponse JSON
      console.log("AJAX Success:", data);
      /* if (data.result[0].indexOf('An error occurred:') === 0) {
        document.getElementById('error-message').textContent = data.result;
        document.getElementById('error-message').style.color = 'red';
      } else {
        // Compléter les champs du formulaire
        console.log(`Token Username : ${data.result.Token_username}`);
        console.log(`Password : ${data.result.Token_Password}`);
        console.log(`URL : ${data.result.Token_URL}`);

        // Sélectionner la valeur du champ "ENT / CAS"
        let entSelect = document.querySelector('[data-l2key="CasEnt"]');
        if (obj.ent !== null) {
          entSelect.value = obj.ent;
        } else {
          entSelect.value = "Aucun"; // Sélectionner "Aucun" si "ent" est "null"
        }
        // Cocher la case "Compte Parent" si nécessaire (exemple de condition)
        let parentCheckbox = document.getElementById('Parent');
        parentCheckbox.checked = true; // ou false selon votre logique
      } */
      if (data.state === 'ok') {
        // Si la réponse est True
        // Suppression des icônes précédentes
        $('#bt_Validate').next('.fa-check-circle').remove();
        // Affichage de la coche verte à droite du bouton
        $('#bt_Validate').after('<i class="fas fa-check-circle" style="color:green;margin-left:5px;"></i>');
      } else {
        // Si la réponse est False
        // Suppression des icônes précédentes
        $('#bt_Validate').next('.fa-times-circle').remove();
        // Affichage de la croix rouge à droite du bouton
        $('#bt_Validate').after('<i class="fas fa-times-circle" style="color:red;margin-left:5px;"></i>');
      }
    }
  });
});


/**************************************
 * Tratement de la réception du QR CODE
 ***************************************/

document.querySelector('.rectangle').addEventListener('paste', function (e) {
  var items = e.clipboardData.items;
  for (var i = 0; i < items.length; i++) {
    if (items[i].type.indexOf('image') !== -1) {
      var blob = items[i].getAsFile();
      var reader = new FileReader();
      reader.onload = function (event) {
        var imageData = event.target.result;
        handleImage(imageData);
      };
      reader.readAsDataURL(blob);
    }
  }
});
document.getElementById('fileInput').addEventListener('change', function (e) {
  var file = e.target.files[0];
  var reader = new FileReader();
  reader.onload = function (event) {
    var imageData = event.target.result;
    handleImage(imageData);
  };
  reader.readAsDataURL(file);
});
document.querySelector('.rectangle').addEventListener('drop', function (e) {
  e.preventDefault();
  e.stopPropagation();
  var file = e.dataTransfer.files[0];
  var reader = new FileReader();
  reader.onload = function (event) {
    var imageData = event.target.result;
    handleImage(imageData);
  };
  reader.readAsDataURL(file);
});

function sendImageToServer(code, pin) {
  // Fonction for send QRcode data to AJAX and python script
  document.querySelector('.fa-hourglass-half').classList.remove('hidden');
  $.ajax({
    type: "POST",
    url: "/plugins/ProJote/core/ajax/ProJote.ajax.php",
    data: {
      action: "ValidateQRCode",
      data: code,
      pin: pin,
      eqlogic: $('.eqLogicAttr[data-l1key=id]').value(),
    },
    dataType: 'json',
    global: false,
    error: function (request, status, error) {
      console.error("AJAX Error:", error);
      document.querySelector('.fa-hourglass-half').classList.add('hidden');
      document.querySelector('.fa-times').classList.remove('hidden');
      document.getElementById('error-message').textContent = 'Une erreur s\'est produite lors de la validation du code QR.';
      document.getElementById('error-message').style.color = 'red';
    },
    success: function (data) {
      document.querySelector('.fa-hourglass-half').classList.add('hidden');
      if (data.state === 'ok') {
        document.querySelector('.fa-check').classList.remove('hidden');
        console.log('résultat du QR code : ', JSON.stringify(data.result[0]));
        if (data.result[0].indexOf('An error occurred:') === 0) {
          document.getElementById('error-message').textContent = data.result;
          document.getElementById('error-message').style.color = 'red';
        } else {
          // Compléter les champs du formulaire
          console.log(`Token Username : ${data.result.Token_username}`);
          console.log(`Password : ${data.result.Token_Password}`);
          console.log(`URL : ${data.result.Token_URL}`);
          // Sélectionner la valeur du champ "ENT / CAS"
          let entSelect = document.querySelector('[data-l2key="CasEnt"]');

          if (obj.ent !== null) {
            entSelect.value = obj.ent;
          } else {
            entSelect.value = "Aucun"; // Sélectionner "Aucun" si "ent" est "null"
          }
          // Cocher la case "Compte Parent" si nécessaire (exemple de condition)
          let parentCheckbox = document.getElementById('Parent');
          parentCheckbox.checked = true; // ou false selon votre logique
        }
      } else {
        console.error(data.result);
        document.getElementById('error-message').textContent = data.result;
        document.getElementById('error-message').style.color = 'red';
      }
      // Exécuter la fonction saveEqLogic après la validation du QR code
      if (typeof saveEqLogic === 'function') {
        saveEqLogic();
      } else {
        console.error("La fonction saveEqLogic n'est pas définie. Vérifier dans la fichier PHP que la fonction plugin tempalte est bien incluse");
      }

    }
  });
}

function resizeImage(imageData, width, height) {
  return new Promise((resolve, reject) => {
    var img = new Image();
    img.onload = function () {
      var canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      var ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, width, height);
      var resizedImageData = canvas.toDataURL('image/png');
      resolve(resizedImageData);
    };
    img.onerror = function () {
      reject(new Error('Failed to load image'));
    };
    img.src = imageData;
  });
}

function displayImage(imageData) {
  var img = document.createElement('img');
  img.src = imageData;
  img.style.border = '5px solid #90EE90'; // Couleur du cadre en vert clair
  var rectangle = document.querySelector('.rectangle');
  if (rectangle) {
    rectangle.innerHTML = '';
    // Créez un élément div pour contenir l'image et le texte
    var container = document.createElement('div');
    container.style.position = 'relative';
    rectangle.appendChild(container);
    // Ajoutez l'image à l'élément div
    container.appendChild(img);
    // Ajoutez ce gestionnaire d'événements pour afficher une fenêtre de demande de code PIN
    img.addEventListener('click', function () {
      var pin = prompt('Veuillez entrer votre code PIN de 4 chiffres :');
      // Vérifiez le code PIN ici
      var pinRegex = /^\d{4}$/;
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
  // Demande le code PIN à l'utilisateur
  var pin = prompt('Veuillez entrer votre code PIN de 4 chiffres :');
  // Vérifie que le code PIN saisi par l'utilisateur contient exactement 4 chiffres
  var pinRegex = /^\d{4}$/;
  if (!pinRegex.test(pin)) {
    alert('Code PIN invalide. Veuillez entrer un code PIN de 4 chiffres.');
    return;
  }
  // Si le code PIN est valide, continue le traitement de l'image
  resizeImage(imageData, 200, 200).then(function (resizedImageData) {
    var img = new Image();
    img.onload = function () {
      // Décoder le code QR à partir de l'image
      var canvas = document.createElement('canvas');
      canvas.width = img.width;
      canvas.height = img.height;
      var ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);
      var imageData = ctx.getImageData(0, 0, img.width, img.height);
      var code = jsQR(imageData.data, imageData.width, imageData.height);
      // Si le code QR est décodé avec succès, afficher les données
      if (code) {
        console.log('Données du code QR :', code.data);
      } else {
        console.log('Impossible de décoder le code QR');
        document.getElementById('error-message').textContent = 'Impossible de décoder le code QR';
      }
      displayImage(resizedImageData);

      sendImageToServer(code.data, pin);
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
  var table = document.getElementById('table_cmd').getElementsByTagName('tbody')[0];
  var rows = table.getElementsByTagName('tr');
  var sortedRows = Array.from(rows).sort((a, b) => {
    var idA = parseInt(a.getAttribute('data-cmd_id'));
    var idB = parseInt(b.getAttribute('data-cmd_id'));
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
    var _cmd = { configuration: {} }
  }
  if (!isset(_cmd.configuration)) {
    _cmd.configuration = {}
  }
  sortTableById();
  var tr = '<tr class="cmd" data-cmd_id="' + init(_cmd.id) + '">'
  tr += '<td class="hidden-xs">'
  tr += '<span class="cmdAttr" data-l1key="id"></span>'
  tr += '</td>'
  tr += '<td>'
  tr += '<div class="input-group">'
  tr += '<input class="cmdAttr form-control input-sm roundedLeft" data-l1key="name" placeholder="{{Nom de la commande}}" style="width: 300px;">';
  tr += '<span class="input-group-btn"><a class="cmdAction btn btn-sm btn-default" data-l1key="chooseIcon" title="{{Choisir une icône}}"><i class="fas fa-icons"></i></a></span>'
  tr += '<span class="cmdAttr input-group-addon roundedRight" data-l1key="display" data-l2key="icon" style="font-size:19px;padding:0 5px 0 0!important;"></span>'
  tr += '</div>'
  tr += '<select class="cmdAttr form-control input-sm" data-l1key="value" style="display:none;margin-top:5px;" title="{{Commande info liée}}">'
  tr += '<option value="">{{Aucune}}</option>'
  tr += '</select>'
  tr += '</td>'
  tr += '<td>'
  tr += '<span class="type" type="' + init(_cmd.type) + '">' + jeedom.cmd.availableType() + '</span>'
  tr += '<span class="subType" subType="' + init(_cmd.subType) + '"></span>'
  tr += '</td>'
  tr += '<td>'
  tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="isVisible" checked/>{{Afficher}}</label> '
  tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="isHistorized" checked/>{{Historiser}}</label> '
  tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="display" data-l2key="invertBinary"/>{{Inverser}}</label> '
  tr += '<div style="margin-top:7px;">'
  tr += '<input class="tooltips cmdAttr form-control input-sm" data-l1key="configuration" data-l2key="minValue" placeholder="{{Min}}" title="{{Min}}" style="width:30%;max-width:80px;display:inline-block;margin-right:2px;">'
  tr += '<input class="tooltips cmdAttr form-control input-sm" data-l1key="configuration" data-l2key="maxValue" placeholder="{{Max}}" title="{{Max}}" style="width:30%;max-width:80px;display:inline-block;margin-right:2px;">'
  if (_cmd.unite !== '') {
    tr += '<input class="tooltips cmdAttr form-control input-sm" data-l1key="unite" placeholder="Unité" title="{{Unité}}" style="width:30%;max-width:80px;display:inline-block;margin-right:2px;">';
  }
  tr += '</div>'
  tr += '</td>'
  tr += '<td>';
  tr += '<span class="cmdAttr" data-l1key="htmlstate"></span>';
  tr += '</td>';
  tr += '<td>'
  if (is_numeric(_cmd.id)) {
    tr += '<a class="btn btn-default btn-xs cmdAction" data-action="configure"><i class="fas fa-cogs"></i></a> '
    tr += '<a class="btn btn-default btn-xs cmdAction" data-action="test"><i class="fas fa-rss"></i> {{Tester}}</a>'
  }
  tr += '<i class="fas fa-minus-circle pull-right cmdAction cursor" data-action="remove" title="{{Supprimer la commande}}"></i></td>'
  tr += '</tr>'
  $('#table_cmd tbody').append(tr)
  var tr = $('#table_cmd tbody tr').last()
  jeedom.eqLogic.buildSelectCmd({
    id: $('.eqLogicAttr[data-l1key=id]').value(),
    filter: { type: 'info' },
    error: function (error) {
      $('#div_alert').showAlert({ message: error.message, level: 'danger' })
    },
    success: function (result) {
      tr.find('.cmdAttr[data-l1key=value]').append(result)
      tr.setValues(_cmd, '.cmdAttr')
      jeedom.cmd.changeType(tr, init(_cmd.subType))
    }
  })
}