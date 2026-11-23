// Réveil de Nostradamus (Cloudflare Worker, formule gratuite).
// Toutes les minutes, il regarde dans la base du dépôt si un relevé de cotes est dû (H-12, H-3, H-45).
// Si oui, il réveille le collecteur GitHub tout de suite (événement « tick »). Sinon il ne fait rien.
// Toutes les 5 minutes autour des coups d'envoi, il le réveille aussi pour les compos et les absents.
//
// Il faut un secret GITHUB_TOKEN (clé GitHub limitée à ce seul dépôt, permission « Contents : lecture et écriture »).
//
// Diagnostic : ouvrir l'adresse du Worker dans un navigateur renvoie son état complet.
//   …workers.dev                        -> ce que le Worker voit à l'instant t (jours lus, relevé dû ou non)
//   …workers.dev/?force=1&cle=<DEBUG_KEY> -> tente un réveil pour de vrai (secret à créer sur le Worker)
// Un réveil réussi renvoie 204. 401/403 = jeton absent, expiré ou sans la bonne permission.

const DEPOT = "gegenet59-prog/nostradamus";
const BRANCHE = "main";
// « attente » = à faire ; « vide » = le collecteur a appelé l'API sans trouver la cote, on peut réessayer.
const A_RELEVER = ["attente", "vide"];

const jourParis = (d) => new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Paris" }).format(d);

async function lireJour(jour, env, journal) {
  const url = `https://api.github.com/repos/${DEPOT}/contents/data/matchs/${jour}.json?ref=${BRANCHE}`;
  try {
    const r = await fetch(url, {
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github.raw+json",
        "User-Agent": "nostradamus-reveil",
      },
    });
    if (r.status === 404) { journal.push(`${jour} : pas encore de fichier`); return []; }
    if (!r.ok) { journal.push(`${jour} : HTTP ${r.status} ${(await r.text()).slice(0, 120)}`); return []; }
    const j = await r.json();
    const liste = Array.isArray(j) ? j : j.matchs || [];
    journal.push(`${jour} : ${liste.length} match(s)`);
    return liste;
  } catch (e) {
    journal.push(`${jour} : ${e.message}`);
    return [];
  }
}

export function quoiFaire(matchs, maintenant) {
  const t = maintenant.getTime();
  let releveDu = false, autourDuMatch = false;
  for (const m of matchs) {
    const ko = Date.parse(m.coup_envoi);
    if (!Number.isFinite(ko)) continue;
    if (ko - 90 * 60000 < t && t < ko + 15 * 60000) autourDuMatch = true;
    for (const r of Object.values(m.releves || {})) {
      // un relevé n'a plus de sens après le coup d'envoi
      if (A_RELEVER.includes(r.etat) && Date.parse(r.prevu) - 60000 <= t && t < ko) releveDu = true;
    }
  }
  return { releveDu, autourDuMatch };
}

async function reveiller(env, raison, journal) {
  for (let essai = 1; essai <= 3; essai++) {
    try {
      const r = await fetch(`https://api.github.com/repos/${DEPOT}/dispatches`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "User-Agent": "nostradamus-reveil",
        },
        body: JSON.stringify({ event_type: "tick", client_payload: { raison } }),
      });
      if (r.status === 204) { journal.push(`réveil (${raison}) : OK`); return 204; }
      const corps = (await r.text()).slice(0, 200);
      journal.push(`réveil (${raison}) essai ${essai} : HTTP ${r.status} ${corps}`);
      // Inutile d'insister : le jeton ne s'améliorera pas dans la minute.
      if (r.status === 401 || r.status === 403 || r.status === 404) return r.status;
    } catch (e) {
      journal.push(`réveil (${raison}) essai ${essai} : ${e.message}`);
    }
    await new Promise((ok) => setTimeout(ok, 700 * essai));
  }
  return 0;
}

// Anti-rebond : la base met une minute à se mettre à jour, on ne veut pas réveiller 3 fois de suite.
async function dejaFait(cle) {
  try { return !!(await caches.default.match(new Request(`https://reveil.invalid/${cle}`))); }
  catch { return false; }   // un cache indisponible ne doit jamais bloquer un réveil
}
async function noter(cle, secondes) {
  try {
    await caches.default.put(new Request(`https://reveil.invalid/${cle}`),
      new Response("1", { headers: { "Cache-Control": `max-age=${secondes}` } }));
  } catch { /* sans importance */ }
}

async function diagnostiquer(env, maintenant) {
  const journal = [];
  const jours = [jourParis(new Date(+maintenant - 86400000)),
                 jourParis(maintenant),
                 jourParis(new Date(+maintenant + 86400000))];
  const matchs = (await Promise.all(jours.map((j) => lireJour(j, env, journal)))).flat();
  return {
    heure: maintenant.toISOString(),
    jeton: env.GITHUB_TOKEN ? "présent" : "ABSENT (pose le secret GITHUB_TOKEN)",
    lectures: journal,
    matchs: matchs.length,
    ...quoiFaire(matchs, maintenant),
  };
}

export default {
  async scheduled(event, env, ctx) {
    const maintenant = new Date();
    const d = await diagnostiquer(env, maintenant);
    const journal = [...d.lectures, `releveDu=${d.releveDu} autourDuMatch=${d.autourDuMatch}`];
    const minute = maintenant.getUTCMinutes();

    if (d.releveDu && !(await dejaFait("releve"))) {
      if ((await reveiller(env, "releve", journal)) === 204) await noter("releve", 100);
    } else if (d.autourDuMatch && minute % 5 === 0 && !(await dejaFait("autour"))) {
      if ((await reveiller(env, "autour", journal)) === 204) await noter("autour", 200);
    }
    console.log("réveil : " + journal.join(" | "));
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    const maintenant = new Date();
    const d = await diagnostiquer(env, maintenant);
    let essai = null;
    if (url.searchParams.get("force") === "1") {
      // Fermé par défaut : sans le secret DEBUG_KEY, le réveil manuel est désactivé. L'adresse du Worker est
      // publique, et rien n'oblige à offrir à n'importe qui un bouton qui lance le collecteur.
      const cle = url.searchParams.get("cle");
      if (!env.DEBUG_KEY) {
        essai = { statut: "désactivé", raison: "réveil manuel désactivé : ajoute un secret DEBUG_KEY au Worker" };
      } else if (cle !== env.DEBUG_KEY) {
        essai = { statut: "refusé", raison: "clé absente ou incorrecte" };
      } else {
        const journal = [];
        essai = { statut: await reveiller(env, "manuel", journal), journal };
      }
    }
    return new Response(JSON.stringify({ ...d, essai }, null, 1), {
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
    });
  },
};
