// Réveil de Nostradamus (Cloudflare Worker, formule gratuite).
// Toutes les minutes, il regarde dans la base du dépôt si un relevé de cotes est dû (H-12, H-3, H-45).
// Si oui, il réveille le collecteur GitHub tout de suite (événement « tick »). Sinon il ne fait rien.
// Toutes les 5 minutes autour des coups d'envoi, il le réveille aussi pour les compos et les absents.
// Il faut un secret GITHUB_TOKEN (clé GitHub limitée à ce seul dépôt, permission « Contents : lecture et écriture »).

const DEPOT = "gegenet59-prog/nostradamus";

const jourParis = (d) => new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Paris" }).format(d); // AAAA-MM-JJ

async function lireJour(jour, env) {
  const r = await fetch(`https://api.github.com/repos/${DEPOT}/contents/data/matchs/${jour}.json`, {
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github.raw+json",
      "User-Agent": "nostradamus-reveil",
    },
  });
  if (!r.ok) return [];
  const j = await r.json();
  return Array.isArray(j) ? j : j.matchs || [];
}

export function quoiFaire(matchs, maintenant) {
  const t = maintenant.getTime();
  let releveDu = false, autourDuMatch = false;
  for (const m of matchs) {
    const ko = Date.parse(m.coup_envoi);
    if (ko - 90 * 60000 < t && t < ko + 15 * 60000) autourDuMatch = true;
    for (const r of Object.values(m.releves || {})) {
      if (r.etat === "attente" && Date.parse(r.prevu) - 60000 <= t && t < ko) releveDu = true;   // un relevé n’a plus de sens après le coup d’envoi
    }
  }
  return { releveDu, autourDuMatch };
}

async function reveiller(env, raison) {
  const r = await fetch(`https://api.github.com/repos/${DEPOT}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "nostradamus-reveil",
    },
    body: JSON.stringify({ event_type: "tick", client_payload: { raison } }),
  });
  console.log(`réveil (${raison}) : ${r.status}`);
  return r.status;
}

async function dejaFait(cle) {            // évite de réveiller 3 fois de suite pour le même relevé (la base met ~1 min à se mettre à jour)
  const req = new Request(`https://reveil.invalid/${cle}`);
  return !!(await caches.default.match(req));
}
async function noter(cle, secondes) {
  await caches.default.put(new Request(`https://reveil.invalid/${cle}`), new Response("1", { headers: { "Cache-Control": `max-age=${secondes}` } }));
}

export default {
  async scheduled(event, env, ctx) {
    const maintenant = new Date();
    const jours = [jourParis(new Date(maintenant - 86400000)), jourParis(maintenant), jourParis(new Date(+maintenant + 86400000))];
    const matchs = (await Promise.all(jours.map((j) => lireJour(j, env)))).flat();
    const { releveDu, autourDuMatch } = quoiFaire(matchs, maintenant);
    const minute = maintenant.getUTCMinutes();
    if (releveDu && !(await dejaFait("releve"))) {
      await reveiller(env, "releve");
      await noter("releve", 100);
    } else if (autourDuMatch && minute % 5 === 0 && !(await dejaFait("autour"))) {
      await reveiller(env, "autour");
      await noter("autour", 200);
    }
  },
  async fetch(request, env) {                // ouvrir l'adresse du Worker dans un navigateur = test à la main
    const maintenant = new Date();
    const matchs = await lireJour(jourParis(maintenant), env);
    return new Response(JSON.stringify({ heure: maintenant.toISOString(), matchs: matchs.length, ...quoiFaire(matchs, maintenant) }, null, 1), { headers: { "content-type": "application/json" } });
  },
};
