import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

// L'identità del repository resta nell'ambiente locale/CI, fuori da Git.
const repository = process.env.ITADB_GITHUB_REPOSITORY;
if (!repository || !/^[\w.-]+\/[\w.-]+$/.test(repository)) {
  throw new Error("Set ITADB_GITHUB_REPOSITORY to the linked GitHub owner/repository");
}

export const partial = "itadb";

export default defineRailway(() => {
  const apiVolume = volume("api-volume", {
    alerts: { usage: { "80": {}, "95": {}, "100": {} } },
    allowOnlineResize: true,
    region: "europe-west4-drams3a",
    sizeMB: 5000,
  });
  const api = service("api", {
    source: github(repository, { branch: "main", checkSuites: true, rootDirectory: "/" }),
    build: {
      buildEnvironment: "V3",
      builder: "DOCKERFILE",
      dockerfilePath: "infra/api.Dockerfile",
    },
    start: "uvicorn itadb.api.app:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log",
    healthcheck: "/health/ready",
    healthcheckTimeout: 300,
    replicas: { "europe-west4-drams3a": 1 },
    // ON_FAILURE e sleepApplication=false sono i default, verificati via API.
    // La CLI 5.62.1 li omette in lettura: esplicitarli produce drift artificiale.
    deploy: {
      limitOverride: { containers: { cpu: 1, memoryBytes: 1000000000 } },
      restartPolicyMaxRetries: 3,
    },
    volumeMounts: { "/app/serving": apiVolume },
    env: {
      ITADB_CORS_ORIGINS: preserve(),
      ITADB_DUCKDB_MEMORY_MB: "256",
      ITADB_DUCKDB_THREADS: "1",
      ITADB_SERVING_CONCURRENCY: "4",
      ITADB_SERVING_DIR: "/app/serving",
      ITADB_SERVING_TIMEOUT_SECONDS: "5",
      PORT: "8000",
      RAILWAY_DOCKERFILE_PATH: "infra/api.Dockerfile",
    },
  });

  return project("itadb", { resources: [api, apiVolume] });
});
