<?php
if (!isConnect('admin')) {
	throw new Exception('{{401 - Accès non autorisé}}');
}

// Déclaration des variables obligatoires
$plugin = plugin::byId('ProJote');
if ($plugin === null) {
	throw new Exception('{{Plugin ProJote non trouvé}}');
}
$eqLogics = eqLogic::byType($plugin->getId());
sendVarToJS('eqType', $plugin->getId());
sendVarToJS('LogLevel', log::convertLogLevel(log::getLogLevel($plugin->getId())));
sendVarToJS('eqLogicId', $eqLogic);

?>

<div class="row row-overflow">
	<!-- Page d'accueil du plugin -->
	<div class="col-xs-12 eqLogicThumbnailDisplay">
		<legend><i class="fas fa-cog"></i> {{Gestion}}</legend>
		<!-- Boutons de gestion du plugin — grandes icônes + libellé court dessous -->
		<style>
			.pj-gestion { display:flex; flex-wrap:wrap; gap:10px; padding:6px 2px; }
			.pj-gestion .pj-tile {
				display:flex; flex-direction:column; align-items:center; justify-content:flex-start;
				width:120px; padding:16px 8px 12px; border-radius:10px; cursor:pointer;
				text-align:center; transition:background .15s ease, transform .1s ease;
			}
			.pj-gestion .pj-tile:hover { background:rgba(127,127,127,.14); transform:translateY(-1px); }
			.pj-gestion .pj-tile i { font-size:44px; line-height:1; margin-bottom:12px; }
			.pj-gestion .pj-tile span { font-size:13px; font-weight:600; }
		</style>
		<div class="eqLogicThumbnailContainer pj-gestion">
			<div class="pj-tile eqLogicAction logoPrimary" data-action="add">
				<i class="fas fa-plus-circle"></i>
				<span>{{Ajouter}}</span>
			</div>
			<div class="pj-tile eqLogicAction logoSecondary" data-action="gotoPluginConf">
				<i class="fas fa-wrench"></i>
				<span>{{Configuration}}</span>
			</div>
			<div class="pj-tile logoSecondary" id="bt_donProJote" title="{{Faire un don}}">
				<i class="fas fa-mug-hot"></i>
				<span>{{Don}}</span>
			</div>
		</div>

		<!-- Modal Don -->
		<div class="modal fade" id="modal_donProJote" tabindex="-1" role="dialog">
			<div class="modal-dialog" role="document">
				<div class="modal-content">
					<div class="modal-header" style="background-color:#8DC63F;border-radius:5px 5px 0 0;">
						<button type="button" class="close" data-dismiss="modal" style="color:#fff;opacity:1;"><span>&times;</span></button>
						<h4 class="modal-title" style="color:#fff;"><i class="fas fa-mug-hot"></i> {{Soutenir ProJote}}</h4>
					</div>
					<div class="modal-body" style="text-align:center;">
						<p style="font-size:1.1em;">{{Ce plugin est gratuit et open-source.}}<br>{{Si vous l'appréciez, et que vous voulez me remercier, offrez moi un café !}}<br><small>{{Ces dons participent au maintien et au développement du plugin.}}</small></p>
						<hr>
						<a href="https://ko-fi.com/aldarande" target="_blank" class="btn btn-warning btn-lg" style="margin:8px;">
							<i class="fas fa-coffee"></i> Ko-fi
						</a>
						<a href="https://github.com/sponsors/Aldarande" target="_blank" class="btn btn-dark btn-lg" style="margin:8px;">
							<i class="fab fa-github"></i> GitHub Sponsors
						</a>
					</div>
				</div>
			</div>
		</div>
		<legend><i class="fas fa-table"></i> {{Mes équipements}}</legend>
		<?php
		if (count($eqLogics) == 0) {
			echo '<br><div class="text-center" style="font-size:1.2em;font-weight:bold;">{{Aucun équipement Template trouvé, cliquer sur "Ajouter" pour commencer}}</div>';
		} else {
			// Champ de recherche
			echo '<div class="input-group" style="margin:5px;">';
			echo '<input class="form-control roundedLeft" placeholder="{{Rechercher}}" id="in_searchEqlogic">';
			echo '<div class="input-group-btn">';
			echo '<a id="bt_resetSearch" class="btn" style="width:30px"><i class="fas fa-times"></i></a>';
			echo '<a class="btn roundedRight hidden" id="bt_pluginDisplayAsTable" data-coreSupport="1" data-state="0"><i class="fas fa-grip-lines"></i></a>';
			echo '</div>';
			echo '</div>';
			// Liste des équipements du plugin
			echo '<div class="eqLogicThumbnailContainer">';
			foreach ($eqLogics as $eqLogic) {
				$opacity = ($eqLogic->getIsEnable()) ? '' : 'disableCard';
				echo '<div class="eqLogicDisplayCard cursor ' . $opacity . '" data-eqLogic_id="' . $eqLogic->getId() . '">';
				echo '<img src="' . $eqLogic->getImage() . '"/>';
				echo '<br>';
				echo '<span class="name">' . $eqLogic->getHumanName(true, true) . '</span>';
				echo '<span class="hiddenAsCard displayTableRight hidden">';
				echo ($eqLogic->getIsVisible() == 1) ? '<i class="fas fa-eye" title="{{Equipement visible}}"></i>' : '<i class="fas fa-eye-slash" title="{{Equipement non visible}}"></i>';
				echo '</span>';
				echo '</div>';
			}
			echo '</div>';
		}
		?>
	</div> <!-- /.eqLogicThumbnailDisplay -->
	<!-- Page de présentation de l'équipement -->
	<div class="col-xs-12 eqLogic" style="display: none;">
		<!-- barre de gestion de l'équipement -->
		<div class="input-group pull-right" style="display:inline-flex;">
			<span class="input-group-btn">
				<!-- Les balises <a></a> sont volontairement fermées à la ligne suivante pour éviter les espaces entre les boutons. Ne pas modifier -->
				<a class="btn btn-sm btn-default eqLogicAction roundedLeft" data-action="configure"><i class="fas fa-cogs"></i><span class="hidden-xs"> {{Configuration avancée}}</span>
				</a><a class="btn btn-sm btn-default eqLogicAction" data-action="copy"><i class="fas fa-copy"></i><span class="hidden-xs"> {{Dupliquer}}</span>
				</a><a class="btn btn-sm btn-success eqLogicAction" data-action="save"><i class="fas fa-check-circle"></i> {{Sauvegarder}}
				</a><a class="btn btn-sm btn-danger eqLogicAction roundedRight" data-action="remove"><i class="fas fa-minus-circle"></i> {{Supprimer}}
				</a>
			</span>
		</div>
		<!-- Onglets -->
		<ul class="nav nav-tabs" role="tablist">
			<li role="presentation"><a href="#" class="eqLogicAction" aria-controls="home" role="tab" data-toggle="tab" data-action="returnToThumbnailDisplay"><i class="fas fa-arrow-circle-left"></i></a></li>
			<li role="presentation" class="active"><a href="#eqlogictab" aria-controls="home" role="tab" data-toggle="tab"><i class="fas fa-tachometer-alt"></i> {{Equipement}}</a></li>
			<li role="presentation"><a href="#eqlogicDisplaytab" aria-controls="profile" role="tab" data-toggle="tab"><i class="fas fa-desktop"></i> {{Affichage}}</a></li>
			<li role="presentation"><a href="#commandtab" aria-controls="home" role="tab" data-toggle="tab"><i class="fas fa-list"></i> {{Commandes}}</a></li>
		</ul>
		<div class="tab-content">
			<!-- Onglet de configuration de l'équipement -->
			<div role="tabpanel" class="tab-pane active" id="eqlogictab">
				<!-- Partie gauche de l'onglet "Equipements" -->
				<!-- Paramètres généraux et spécifiques de l'équipement -->
				<form class="form-horizontal">
					<fieldset>
						<div class="col-lg-6">
							<legend><i class="fas fa-wrench"></i> {{Paramètres généraux}}</legend>
							<div class="form-group">
								<label class="col-sm-4 control-label">{{Nom de l'équipement}}</label>
								<div class="col-sm-6">
									<input type="text" class="eqLogicAttr form-control" data-l1key="id" style="display:none;">
									<input type="text" class="eqLogicAttr form-control" data-l1key="name" placeholder="{{Nom de l'équipement}}">
								</div>
							</div>
							<div class="form-group">
								<label class="col-sm-4 control-label">{{Objet parent}}</label>
								<div class="col-sm-6">
									<select id="sel_object" class="eqLogicAttr form-control" data-l1key="object_id">
										<option value="">{{Aucun}}</option>
										<?php
										$options = '';
										foreach ((jeeObject::buildTree(null, false)) as $object) {
											$options .= '<option value="' . $object->getId() . '">' . str_repeat('&nbsp;&nbsp;', $object->getConfiguration('parentNumber')) . $object->getName() . '</option>';
										}
										echo $options;
										?>
									</select>
								</div>
							</div>
							<div class="form-group">
								<label class="col-sm-4 control-label">{{Catégorie}}</label>
								<div class="col-sm-6">
									<?php
									foreach (jeedom::getConfiguration('eqLogic:category') as $key => $value) {
										echo '<label class="checkbox-inline">';
										echo '<input type="checkbox" class="eqLogicAttr" data-l1key="category" data-l2key="' . $key . '" >' . $value['name'];
										echo '</label>';
									}
									?>
								</div>
							</div>
							<div class="form-group">
								<label class="col-sm-4 control-label">{{Options}}</label>
								<div class="col-sm-6">
									<label class="checkbox-inline"><input type="checkbox" class="eqLogicAttr" data-l1key="isEnable" checked>{{Activer}}</label>
									<label class="checkbox-inline"><input type="checkbox" class="eqLogicAttr" data-l1key="isVisible" checked>{{Visible}}</label>
								</div>
							</div>
							<div class="form-group auth-parameters">
								<div class="row align-items-center"> <!-- Utilisation d'un conteneur de ligne -->
									<legend class="col-sm-7"><i class="fas fa-cogs"></i> {{Paramètres d'authentification}}</legend>
									<div class="col-sm-3"> <!-- Ajustez la largeur selon vos besoins -->
										<select class="eqLogicAttr form-control" data-l1key="configuration" data-l2key="AUTH">
											<option value="Login" selected>{{Login}}</option> <!-- Valeur par défaut -->
											<option value="QRCode">{{QR Code}}</option>
										</select>
									</div>
								</div>
							</div>
							<div class="form-group Login" style="display:none;">
								<legend><i class="fa fa-user"></i> {{Login}}
									<i class="fas fa-hourglass-half fa-spin hidden"></i>
									<i class="fas fa-check hidden"></i>
									<i class="fas fa-times hidden"></i>
								</legend>
								<div class="form-group ENT">
									<label class="col-sm-4 control-label">{{ENT / CAS}}<i class="fas fa-question-circle tooltips" title="{{Renseignez le CAS ENT qui correspond à ce compte}}"></i></label>
									<select type="text" class="col-sm-6 eqLogicAttr form-control" data-l1key="configuration" data-l2key="CasEnt">
										<option value="">{{Aucun}}</option>
										<option value="pronotepy.ent">{{pronotepy.ent}}</option>
										<option value="ac_orleans_tours">{{ac_orleans_tours}}</option>
										<option value="ac_poitiers">{{ac_poitiers}}</option>
										<option value="ac_reunion">{{ac_reunion}}</option>
										<option value="ac_reims">{{ac_reims}}</option>
										<option value="ac_rennes">{{ac_rennes}}</option>
										<option value="atrium_sud">{{atrium_sud}}</option>
										<option value="cas_agora06">{{cas_agora06}}</option>
										<option value="cas_arsene76_edu">{{cas_arsene76_edu}}</option>
										<option value="cas_cybercolleges42_edu">{{cas_cybercolleges42_edu}}</option>
										<option value="cas_kosmos">{{cas_kosmos}}</option>
										<option value="cas_seinesaintdenis_edu">{{cas_seinesaintdenis_edu}}</option>
										<option value="eclat_bfc">{{eclat_bfc}}</option>
										<option value="ecollege_haute_garonne_edu">{{ecollege_haute_garonne_edu}}</option>
										<option value="ent_94">{{ent_94}}</option>
										<option value="ent_auvergnerhonealpe">{{ent_auvergnerhonealpe}}</option>
										<option value="ent_creuse">{{ent_creuse}}</option>
										<option value="ent_creuse_educonnect">{{ent_creuse_educonnect}}</option>
										<option value="ent_elyco">{{ent_elyco}}</option>
										<option value="ent_essonne">{{ent_essonne}}</option>
										<option value="ent_hdf">{{ent_hdf}}</option>
										<option value="ent_mayotte">{{ent_mayotte}}</option>
										<option value="ent_somme">{{ent_somme}}</option>
										<option value="ent_var">{{ent_var}}</option>
										<option value="ent77">{{ent77}}</option>
										<option value="ent_ecollege78">{{ent_ecollege78}}</option>
										<option value="extranet_colleges_somme">{{extranet_colleges_somme}}</option>
										<option value="ile_de_france">{{ile_de_france}}</option>
										<option value="laclasse_educonnect">{{laclasse_educonnect}}</option>
										<option value="laclasse_lyon">{{laclasse_lyon}}</option>
										<option value="l_normandie">{{l_normandie}}</option>
										<option value="lyceeconnecte_aquitaine">{{lyceeconnecte_aquitaine}}</option>
										<option value="lyceeconnecte_edu">{{lyceeconnecte_edu}}</option>
										<option value="monbureaunumerique">{{monbureaunumerique}}</option>
										<option value="neoconnect_guadeloupe">{{neoconnect_guadeloupe}}</option>
										<option value="occitanie_montpellier">{{occitanie_montpellier}}</option>
										<option value="occitanie_montpellier_educonnect">{{occitanie_montpellier_educonnect}}</option>
										<option value="occitanie_toulouse_edu">{{occitanie_toulouse_edu}}</option>
										<option value="ozecollege_yvelines">{{ozecollege_yvelines}}</option>
										<option value="paris_classe_numerique">{{paris_classe_numerique}}</option>
										<option value="pronote_hubeduconnect">{{pronote_hubeduconnect}}</option>
										<option value="val_de_marne">{{val_de_marne}}</option>
										<option value="val_doise">{{val_doise}}</option>
									</select>
								</div>
								<div class="form-group">
									<label class="col-sm-4 control-label">{{Type de compte}}<i class="fas fa-question-circle tooltips" title="{{Choisissez le type de compte : élève ou parent}}"></i></label>
									<div class="col-sm-6">
										<label class="radio-inline"><input type="radio" name="accountType" value="eleve" class="eqLogicAttr" data-l1key="configuration" data-l2key="accountType" checked> {{Élève}}</label>
										<label class="radio-inline"><input type="radio" name="accountType" value="parent" class="eqLogicAttr" data-l1key="configuration" data-l2key="accountType"> {{Parent}}</label>
									</div>
								</div>
								<div class="form-group">
									<label class="col-sm-4 control-label">{{Login du compte}}<i class="fas fa-question-circle tooltips" title="{{Renseignez le login pour vous connecter à Pronote}}"></i></label>
									<input type="text" class="col-sm-6 eqLogicAttr form-control" data-l1key="configuration" data-l2key="login" autocomplete="username">
								</div>
								<div class="form-group">
									<label class="col-sm-4 control-label">{{Mot de passe}}<i class="fas fa-question-circle tooltips" title="{{Renseignez le mot de passe}}"></i></label>
									<input type="password" class=" col-sm-6 eqLogicAttr form-control inputPassword" data-l1key="configuration" data-l2key="password" autocomplete="current-password">
								</div>
								<div class="form-group">
									<label class="col-sm-4 control-label">{{Url}}<i class="fas fa-question-circle tooltips" title="{{Renseignez l'adresse web pour vous connecter à Pronote}}"></i></label>
									<input type="text" class="col-sm-6 eqLogicAttr form-control" data-l1key="configuration" data-l2key="url" autocomplete="off">
								</div>

								<div class="form-group Validate">
									<div class="form-group">
										<div class="col-sm-6 col-sm-offset-4 control-label">
											<a class="eqLogicAttr btn btn-sm btn-success eqLogicAction" id="bt_Validate"><i class="fas fa-check-circle"></i> {{Valider}}</a>
										</div>
									</div>
								</div>
							</div>
							<div class="form-group QRCode" style="display:none;">
								<legend>
									<i class="fas fa-qrcode"></i> {{Qr Code}}
									<i class="fas fa-hourglass-half fa-spin hidden"></i>
									<i class="fas fa-check hidden"></i>
									<i class="fas fa-times hidden"></i>
								</legend>
								<div class="form-group">
									<label class="col-sm-3 control-label"></label>
									<div class="col-sm-6">
										<div class="rectangle eqLogicAction" contenteditable="true">
											<input type="file" id="fileInput" style="display:none;">
											<label for="fileInput" class="button">Parcourir</label>
										</div>
									</div>
								</div>
							</div>
							<div class="form-group listenfant" style="display:none;">
								<legend>
									<i class="fas fa-users"></i> {{Liste des élèves}}
								</legend>
								<div class="form-group">
									<label class="col-sm-4 control-label">{{Enfants}} <i class="fas fa-question-circle tooltips" title="{{Choisissez le nom de l'enfant}}"></i></label>
									<div class="col-sm-6">
										<div class="input-group">
											<select id="enfantlist" class="eqLogicAttr form-control" data-l1key="configuration" data-l2key="enfant"></select>
											<span class="input-group-btn">
												<a class="btn btn-default" id="bt_renameEqLogic" title="{{Appliquer la sélection et synchroniser avec Pronote}}">
													<i class="fas fa-sync-alt" id="bt_renameEqLogic_icon"></i>
													<i class="fas fa-hourglass-half fa-spin hidden" id="bt_renameEqLogic_spin"></i>
												</a>
											</span>
										</div>
									</div>
								</div>
							</div>
							<div class="form-group text-center" id="error-message" style="color: red; font-weight: bold;text-align: center; margin: 0 auto;"></div>
						</div>

						<!-- Partie droite de l'onglet "Équipement" -->
						<!-- Affiche un champ de commentaire par défaut mais vous pouvez y mettre ce que vous voulez -->
						<div class="col-lg-6">
							<legend><i class="col-sm-1 fas fa-info"></i> {{Informations}}</legend>
							<div class="form-group description">
								<label class="col-sm-2 control-label">{{Description}}</label>
								<div class="col-sm-10">
									<textarea class="form-control eqLogicAttr autogrow" data-l1key="comment"></textarea>
								</div>
							</div>
							<!-- Section du Eleve -->
							<div class="form-group Eleve">
								<legend><i class="col-sm-1 fas fa-address-card"></i> {{Elève}} </legend>
								<div class="row">
									<div class="col-sm-8">
										<div class="form-group">
											<label class="col-sm-4 control-label">{{Nom de l'élève}} :</label>
											<div class="col-sm-8">
												<span id="eleve-name" class="eqLogicAttr" data-l1key="configuration" data-l2key="Eleve"></span>
											</div>
										</div>
										<div class="form-group">
											<label class="col-sm-4 control-label">{{Classe}} :</label>
											<div class="col-sm-8">
												<span id="eleve-classe" class="eqLogicAttr" data-l1key="configuration" data-l2key="Classe"></span>
											</div>
										</div>
										<div class="form-group">
											<label class="col-sm-4 control-label">{{Établissement}} :</label>
											<div class="col-sm-8">
												<span id="eleve-etablissement" class="eqLogicAttr" data-l1key="configuration" data-l2key="Etablissement"></span>
											</div>
										</div>
									</div>
									<div class="col-sm-4 text-center">
										<label class="control-label">{{Photo de l'élève}} :</label>
										<div>
											<img id="local-picture" src="" alt="Photo de l'élève" style="max-width: 200px; max-height: 200px; display: none;">
										</div>
									</div>
								</div>
							</div>
							<div class="form-group Token" style="display: none;">
								<!-- Section du Token -->
								<legend><i class="col-sm-1 fas fa-file-code"></i> {{Token Info}} </legend>
								<div class="form-group">
									<label class="col-sm-2 control-label">{{pronote_url}} :</label>
									<span id="Token_pronote_url" class="col-sm-10"></span>
								</div>
								<div class="form-group">
									<label class="col-sm-2 control-label">{{username}} :</label>
									<span id="Token_username" class="col-sm-10"></span>
								</div>
								<div class="form-group">
									<label class="col-sm-2 control-label">{{password}} :</label>
									<span id="Token_password" class="col-sm-10"></span>
								</div>
								<div class="form-group">
									<label class="col-sm-2 control-label">{{client_identifier}} :</label>
									<span id="Token_client_identifier" class="col-sm-10"></span>
								</div>
							</div>
						</div>
			</div>
			</fieldset>
			</form>
			<!-- /.tabpanel #eqlogictab-->
			<!-- Onglet des commandes de l'équipement -->
			<div role="tabpanel" class="tab-pane" id="commandtab">
				<a class="btn btn-default btn-sm pull-right cmdAction" data-action="add" style="margin-top:5px;"><i class="fas fa-plus-circle"></i> {{Ajouter une commande}}</a>
				<br><br>
				<div class="table-responsive">
					<table id="table_cmd" class="table table-bordered table-condensed" style="table-layout:fixed;width:100%;">
						<colgroup>
							<col style="width:50px;">
							<col style="width:220px;">
							<col><!-- Valeur : prend le reste -->
							<col style="width:120px;">
							<col style="width:120px;">
						</colgroup>
						<thead>
							<tr>
								<th>{{#}}</th>
								<th>{{Nom}}</th>
								<th>{{Valeur}}</th>
								<th>{{Options}}</th>
								<th>{{Actions}}</th>
							</tr>
						</thead>
						<tbody>
						</tbody>
					</table>
				</div>
			</div><!-- /.tabpanel #commandtab-->
		<div role="tabpanel" class="tab-pane" id="eqlogicDisplaytab">
			<div class="row" style="margin-top:12px;">

				<!-- ── Colonne gauche : paramètres du widget + photo manuelle ── -->
				<div class="col-sm-5">
					<form class="form-horizontal">
						<fieldset>
							<legend><i class="fas fa-paint-brush"></i> {{Personnalisation du widget}}</legend>

							<div class="form-group">
								<label class="col-sm-6 control-label">{{Couleur d'accentuation}}</label>
								<div class="col-sm-5">
									<input type="color" class="eqLogicAttr form-control" data-l1key="display" data-l2key="parameters_accent_color" value="#94C904">
								</div>
							</div>

							<div class="form-group">
								<label class="col-sm-6 control-label">{{Taille de police}}</label>
								<div class="col-sm-5">
									<select class="eqLogicAttr form-control" data-l1key="display" data-l2key="parameters_font_size">
										<option value="10px">10</option>
										<option value="11px">11</option>
										<option value="12px" selected>12 ({{défaut}})</option>
										<option value="13px">13</option>
										<option value="14px">14</option>
										<option value="15px">15</option>
										<option value="16px">16</option>
									</select>
								</div>
							</div>

							<div class="form-group">
								<label class="col-sm-6 control-label">{{Onglet par défaut}}</label>
								<div class="col-sm-5">
									<select class="eqLogicAttr form-control" data-l1key="display" data-l2key="parameters_default_tab">
										<option value="dv" selected>{{Devoirs}}</option>
										<option value="notes">{{Notes}}</option>
										<option value="abs">{{Absences}}</option>
										<option value="ret">{{Retards}}</option>
										<option value="pun">{{Punitions}}</option>
									</select>
								</div>
							</div>

							<div class="form-group">
								<label class="col-sm-6 control-label">{{Navigation EDT}}</label>
								<div class="col-sm-5">
									<select class="eqLogicAttr form-control" data-l1key="display" data-l2key="parameters_edt_nav_mode">
										<option value="next_day" selected>{{Seulement J+1}}</option>
										<option value="arrows">{{Jusqu'à J+4}}</option>
									</select>
								</div>
							</div>

						</fieldset>

						<fieldset style="margin-top:15px;">
							<legend><i class="fas fa-user-circle"></i> {{Photo de profil}}</legend>

							<!-- Miniatures Pronote | Manuelle -->
							<div style="display:flex;gap:20px;padding:0 15px 12px;flex-wrap:wrap;">

								<!-- Photo Pronote (lecture seule) -->
								<div style="text-align:center;">
									<div style="font-size:10px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px;">Pronote</div>
									<div id="pjw-pronote-photo-wrap" style="display:none;width:70px;height:70px;">
										<img id="pjw-pronote-photo-img" src="" alt="" style="width:70px;height:70px;border-radius:50%;border:2px solid #ccc;object-fit:cover;">
									</div>
									<div id="pjw-no-pronote-photo" class="text-muted" style="font-size:11px;line-height:70px;">{{Aucune}}</div>
								</div>

								<!-- Photo manuelle (upload utilisateur) -->
								<div style="text-align:center;">
									<div style="font-size:10px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px;">{{Manuelle}}</div>
									<div id="pjw-manual-photo-wrap" style="display:none;position:relative;width:70px;height:70px;">
										<img id="pjw-manual-photo-img" src="" alt="" style="width:70px;height:70px;border-radius:50%;border:2px solid #ccc;object-fit:cover;">
										<button type="button" id="pjw-manual-photo-delete"
											style="position:absolute;top:-5px;right:-5px;width:20px;height:20px;border-radius:50%;padding:0;line-height:18px;font-size:10px;"
											class="btn btn-xs btn-danger" title="{{Supprimer la photo manuelle}}">
											<i class="fas fa-times"></i>
										</button>
									</div>
									<div id="pjw-no-manual-photo" class="text-muted" style="font-size:11px;line-height:70px;">{{Aucune}}</div>
									<label class="btn btn-xs btn-default" style="margin-top:4px;cursor:pointer;display:block;width:70px;">
										<i class="fas fa-plus"></i>
										<input type="file" id="pjw-manual-photo-input" accept="image/jpeg,image/png,image/webp" style="display:none;">
									</label>
								</div>

							</div>

							<!-- Selecteur source photo -->
							<div class="form-group" style="margin-bottom:4px;">
								<label class="col-sm-6 control-label" style="font-size:12px;">{{Photo a utiliser}}</label>
								<div class="col-sm-6">
									<select class="eqLogicAttr form-control input-sm" data-l1key="configuration" data-l2key="photo_source">
										<option value="none" selected>{{Aucune (initiales)}}</option>
										<option value="pronote">{{Photo Pronote}}</option>
										<option value="manual">{{Photo manuelle}}</option>
										<option value="auto">{{Automatique (Pronote en priorite)}}</option>
									</select>
								</div>
							</div>

							<div id="pjw-manual-photo-status" style="font-size:11px;margin-top:8px;padding:0 15px;clear:both;"></div>
						</fieldset>
					</form>
				</div>

				<!-- ── Colonne droite : prévisualisation du widget ── -->
				<div class="col-sm-7">
					<fieldset>
						<legend><i class="fas fa-eye"></i> {{Prévisualisation du widget}}</legend>
						<p class="text-muted" style="font-size:11px;margin-bottom:8px;">{{Sauvegardez l'équipement puis cliquez sur Rafraîchir pour voir vos modifications.}}</p>
						<div id="pjw-preview-zone" style="min-height:150px;border:1px dashed #ccc;border-radius:6px;padding:10px;background:#f9f9f9;overflow:auto;display:flex;align-items:center;justify-content:center;">
							<span class="text-muted" style="font-size:12px;">{{Cliquez sur Rafraîchir pour charger la prévisualisation}}</span>
						</div>
						<button type="button" id="pjw-preview-refresh" class="btn btn-sm btn-default" style="margin-top:8px;">
							<i class="fas fa-sync"></i> {{Rafraîchir}}
						</button>
					</fieldset>
				</div>

			</div><!-- /.row -->
		</div><!-- /.tabpanel #eqlogicDisplaytab -->
		</div><!-- /.tab-content -->
	</div><!-- /.eqLogic -->
</div><!-- /.row row-overflow -->
<!-- Inclusion du fichier javascript du plugin (dossier, nom_du_fichier, extension_du_fichier, id_du_plugin) -->
<?php include_file('desktop', 'ProJote', 'js', 'ProJote'); ?>
<?php include_file('3rdparty', 'jsQR', 'js', 'ProJote'); ?>
<!-- Inclusion du fichier javascript du core - NE PAS MODIFIER NI SUPPRIMER -->
<?php include_file('core', 'plugin.template', 'js'); ?>
<style>
	.rectangle {
		width: 200px;
		height: 200px;
		background-color: lightgray;
		display: flex;
		justify-content: center;
		align-items: center;
		cursor: pointer;
	}

	#error-message {
		color: red;
		font-weight: bold;
		text-align: center;
	}

	.button {
		padding: 10px;
		/* background-color: white; */
		cursor: pointer;
	}

	.fa-spin {
		animation: fa-spin 2s infinite linear;
	}

	.fa-check {
		color: green;
	}

	.fa-times {
		color: red;
	}

	.hidden {
		display: none;
	}

	@keyframes fa-spin {
		0% {
			transform: rotate(0deg);
		}

		100% {
			transform: rotate(360deg);
		}
	}

	.small-font {
		font-size: 12px;
		/* Ajustez la taille selon vos besoins */
	}

	.url-link {
		text-decoration: none;
		/* Supprime le soulignement par défaut */
		color: #007bff;
		/* Couleur du lien */
		position: relative;
		top: +5px;
		left: +5px;
		display: inline-block;
		width: 100%;
	}

	.url-link:hover {
		text-decoration: underline;
		/* Souligne le lien au survol */
	}

	.token-url-container {
		display: flex;
		flex-direction: column;
	}

	.token-url-label {
		margin-bottom: 5px;
		/* Ajustez l'espacement entre les lignes */
	}

	.scrollable-container {
		overflow-x: auto;
		/* Permet le défilement horizontal */
		white-space: nowrap;
		/* Empêche le texte de passer à la ligne */
	}
</style>