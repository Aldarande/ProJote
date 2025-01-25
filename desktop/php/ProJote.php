<?php
if (!isConnect('admin')) {
	throw new Exception('{{401 - Accès non autorisé}}');
}

// Déclaration des variables obligatoires
$plugin = plugin::byId('ProJote');
sendVarToJS('eqType', $plugin->getId());
$eqLogics = eqLogic::byType($plugin->getId());
define('FILE_PATH', '/var/www/html/plugins/ProJote/data/');
function generateFormGroup($label, $input, $tooltip = '')
{
	return '<div class="form-group">
                <label class="col-sm-4 control-label">' . $label . '
                    <sup><i class="fas fa-question-circle tooltips" title="' . $tooltip . '"></i></sup>
                </label>
                <div class="col-sm-6">' . $input . '</div>
            </div>';
}
?>

<div class="row row-overflow">
	<!-- Page d'accueil du plugin -->
	<div class="col-xs-12 eqLogicThumbnailDisplay">
		<legend><i class="fas fa-cog"></i> {{Gestion}}</legend>
		<!-- Boutons de gestion du plugin -->
		<div class="eqLogicThumbnailContainer">
			<div class="cursor eqLogicAction logoPrimary" data-action="add">
				<i class="fas fa-plus-circle"></i>
				<br>
				<span>{{Ajouter}}</span>
			</div>
			<div class="cursor eqLogicAction logoSecondary" data-action="gotoPluginConf">
				<i class="fas fa-wrench"></i>
				<br>
				<span>{{Configuration}}</span>
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
									<label class="col-sm-4 control-label">{{Compte Parent}}<i class="fas fa-question-circle tooltips" title="{{Cochez si vous utilisez une compte parent, donc pas un compte élève}}"></i></label>
									<input type="checkbox" id="Parent" class="eqLogicAttr form-control" data-l1key="configuration" data-l2key="CptParent">
								</div>
								<div class=" form-group">
									<label class="col-sm-4 control-label">{{Login du compte}}<i class="fas fa-question-circle tooltips" title="{{Renseignez le login pour vous connecter à Pronote}}"></i></label>
									<input type="text" class="col-sm-6 eqLogicAttr form-control" data-l1key="configuration" data-l2key="login">
								</div>
								<div class="form-group">
									<label class="col-sm-4 control-label">{{Mot de passe}}<i class="fas fa-question-circle tooltips" title="{{Renseignez le mot de passe}}"></i></label>
									<input type="password" class=" col-sm-6 eqLogicAttr form-control inputPassword" data-l1key="configuration" data-l2key="password">
								</div>
								<div class="form-group">
									<label class="col-sm-4 control-label">{{Url }}<i class="fas fa-question-circle tooltips" title="{{Renseignez l'adresse web pour vous connecter à Pronote}}"></i></label>
									<input type="text" class="col-sm-6 eqLogicAttr form-control" data-l1key="configuration" data-l2key="url">
								</div>
								<div class="form-group listenfant" style="display:block;">
									<label class="col-sm-4 control-label">{{Enfants }} <i class="fas fa-question-circle tooltips" title="{{Choisissez le nom de l'enfant}}"></i></label>
									<select id="enfantList" class="col-sm-6 eqLogicAttr form-control" data-l1key="configuration" data-l2key="enfant"></select>
									<!-- Liste des enfants provisionnée en JS via -->

								</div>
								<div class="form-group Validate">
									<div class=" form-group">
										<div class="col-sm-6 col-sm-offset-4 control-label">
											<a class="btn btn-sm btn-success eqLogicAction" id="bt_Validate"><i class="fas fa-check-circle"></i> {{Valider}}</a>
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
							<div class="form-group text-center" id="error-message" style="color: red; font-weight: bold;text-align: center; margin: 0 auto;"></div>
						</div>
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
						</style>
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
							<!-- Section du Token 
							 
							<div style="display:none;" class="form-group Token">
								<input type="hidden" id="eqLogicId" value="<?php echo $eqLogic->getId(); ?>">
								<legend>
									<i class="col-sm-1 fa fa-compress"></i> {{Token}}
									<sup>
										<i class="fas fa-question-circle tooltips" title="{{Il s'agit des informations servant à la connexion obtenue.}}"></i>
									</sup>
								</legend>
								<div id="error-message" style="color: red; font-weight: bold;"></div>
								<div class="form-group">
									<label class="col-sm-2 control-label">{{Username}} :</label>
									<div class="col-sm-10">
										<span id="token-username" style="position:relative;top:+5px;left:+5px;" class="eqLogicAttr small-font"></span>
									</div>
								</div>
								<div class="form-group">
									<label class="col-sm-2 control-label">{{Token_Pass}} :</label>
									<div class="col-sm-10 scrollable-container">
										<span id="token-password" style="position:relative;top:+5px;left:+5px;display:inline-block;" class="eqLogicAttr  small-font scrollable-container"></span>
									</div>
								</div>
								<div class="form-group">
									<label class="eqLogicAttr col-sm-2 control-label">{{Token_URL}} :</label>
									<div style="scrollbar-width: none;" class="col-sm-10 scrollable-container">
										<a id="token-url" href="#" target="_blank" class="eqLogicAttr url-link small-font scrollable-container"></a>
									</div>
								</div>
							</div> -->
							<!-- Section du Eleve -->
							<div class="form-group Eleve">
								<legend><i class="col-sm-1 fas fa-info"></i> {{Elève}} </legend>
								<div class="form-group">
									<label class="col-sm-2 control-label">{{Nom de l'élève}} :</label>
									<span id="eleve-name"></span>
								</div>
								<div class="form-group">
									<label class="col-sm-2 control-label">{{Classe}} :</label>
									<span id="eleve-classe"></span>
								</div>
								<div class="form-group">
									<label class="col-sm-2 control-label">{{Établissement}} :</label>
									<span id="eleve-etablissement"></span>
								</div>
								<div class="form-group">
									<label class="col-sm-2 control-label">{{Photo de l'élève}} : </label>
									<div class="text-center">
										<img id="local-picture" src="" alt="Photo de l'élève" style="max-width: 200px; max-height: 200px; display: none;">
									</div>
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
					<table id="table_cmd" class="table table-bordered table-condensed">
						<thead>
							<tr>
								<th class="hidden-xs" style="min-width:30px;width:50px;">ID</th>
								<th style="min-width:200px;width:250px;">{{Nom}}</th>
								<th>{{Type}}</th>
								<th style="min-width:500px;">{{Options}}</th>
								<th>{{Etat}}</th>
								<th style="min-width:80px;width:200px;">{{Actions}}</th>
							</tr>
						</thead>
						<tbody>
						</tbody>
					</table>
				</div>
			</div><!-- /.tabpanel #commandtab-->
		</div><!-- /.tab-content -->
	</div><!-- /.eqLogic -->
</div><!-- /.row row-overflow -->
<!-- Inclusion du fichier javascript du plugin (dossier, nom_du_fichier, extension_du_fichier, id_du_plugin) -->
<?php include_file('desktop', 'ProJote', 'js', 'ProJote'); ?>
<?php include_file('3rdparty', 'jsQR', 'js', 'ProJote'); ?>
<!-- Inclusion du fichier javascript du core - NE PAS MODIFIER NI SUPPRIMER -->
<?php include_file('core', 'plugin.template', 'js'); ?>

<style>
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
</div>