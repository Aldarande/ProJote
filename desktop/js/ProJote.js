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

// Ajout de l'événement de clic sur le bouton Valider
$('#bt_Validate').on('click', function () {
  // Récupération des données
  // Récupérer les valeurs des éléments
  let Url = document.querySelector('[data-l2key="url"]').value;
  let Login = document.querySelector('[data-l2key="login"]').value;
  let Password = document.querySelector('[data-l2key="password"]').value;
  let CasEnt = document.querySelector('[data-l2key="CasEnt"]').value;

  // Transformer en un tableau d'objets
  let dataLogin = [
    { 'url': Url },
    { 'login': Login },
    { 'password': Password },
    { 'ent': CasEnt }
  ];
  //A supprimer ....
  console.log("AJAX Log DataLogin : ", dataLogin);
  // Exécution de la requête AJAX
  $.ajax({
    type: "POST", // Méthode de transmission des données au fichier php
    url: "/plugins/ProJote/core/ajax/ProJote.ajax.php", // URL du script PHP AJAX
    data: {
      action: "Validate", // Action à exécuter dans le script PHP
      url: Url,
      login: Login,
      password: Password,
      ent: CasEnt
    },
    dataType: 'json',
    global: false,
    error: function (request, status, error) {
      // Gestion des erreurs
      console.error("AJAX Error:", error);
      $('#bt_Validate').next('.fa-check-circle').remove();
      // Affichage de la croix rouge à droite du bouton
      $('#bt_Validate').after('<i class="fas fa-times-circle" style="color:red;margin-left:5px;"></i>');
    },
    success: function (data) {
      // Traitement de la réponse JSON
      console.log("AJAX Success:", data);
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
      if (data === 'True') {
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

function prePrintEqLogic(_eqlogicId) {
  $.ajax({
    type: "POST",
    url: "plugins/ProJote/core/ajax/ProJote.ajax.php",
    data: {
      action: "GetEquipmentInfo",
      id: _eqlogicId
    },
    dataType: 'json',
    success: function (response) {
      console.log('Réponse de la requête AJAX :', response);
      // Vérifier si la propriété 'result' est définie et est un tableau
      if (response.result && Array.isArray(response.result)) {
        if (is_object(selectElement = document.getElementById('enfantList'))) {
          response.result.forEach(item => {
            if (item.trim() !== '') {
              var option = document.createElement('option');
              option.value = item;
              option.textContent = item;
              selectElement.appendChild(option);
            }
          });
        }
      } else {
        console.warn('La propriété \'result\' n\'est pas un tableau, affichage de la première ligne :');
        console.log(response.result); // Afficher la première ligne
      }
    },
    error: function (jqXHR, textStatus, errorThrown) {
      console.error('Erreur lors de la récupération des informations de l\'équipement :', textStatus, errorThrown);
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

    // Ajoutez ce message "Cliquez pour valider" en vert gras, centré verticalement et horizontalement
    /*     var message = document.createElement('div');
        message.textContent = 'Cliquez pour valider';
        message.style.color = '#90EE90'; // Couleur du texte en vert clair
        message.style.fontWeight = 'bold'; // Texte en gras
        message.style.position = 'absolute';
        message.style.top = '50%';
        message.style.left = '50%';
        message.style.transform = 'translate(-50%, -50%)';
        container.appendChild(message); */

    // Ajoutez ce gestionnaire d'événements pour afficher une fenêtre de demande de code PIN
    /* img.addEventListener('click', function () {
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
    }); */
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
      pin: pin
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
    }
  });
}



/* Permet la réorganisation des commandes dans l'équipement */
$("#table_cmd").sortable({
  axis: "y",
  cursor: "move",
  items: ".cmd",
  placeholder: "ui-state-highlight",
  tolerance: "intersect",
  forcePlaceholderSize: true
})

function prePrintEqLogic(_eqlogicId) {
  document.getElementById('div_pageContainer')?.querySelector('.eqLogicAttr[data-l1key="configuration"][data-l2key="enfant"]').jeeValue(0)
}

// Fonction pour trier les lignes de la table par ID croissant
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
/* Fonction permettant l'affichage des commandes dans l'équipement */
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