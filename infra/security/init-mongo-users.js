const databaseName = process.env.MONGO_DB;
const applicationUser = process.env.MONGO_APP_USER;
const applicationPassword = process.env.MONGO_APP_PASSWORD;
const reportUser = process.env.MONGO_REPORT_USER;
const reportPassword = process.env.MONGO_REPORT_PASSWORD;
const backupUser = process.env.MONGO_BACKUP_USER;
const backupPassword = process.env.MONGO_BACKUP_PASSWORD;

if (
  !databaseName ||
  !applicationUser ||
  !applicationPassword ||
  !reportUser ||
  !reportPassword ||
  !backupUser ||
  !backupPassword
) {
  throw new Error("Faltan variables para crear los usuarios MongoDB.");
}

const applicationDatabase = db.getSiblingDB(databaseName);
applicationDatabase.createUser({
  user: applicationUser,
  pwd: applicationPassword,
  roles: [{ role: "readWrite", db: databaseName }],
});
applicationDatabase.createUser({
  user: reportUser,
  pwd: reportPassword,
  roles: [{ role: "read", db: databaseName }],
});
db.getSiblingDB("admin").createUser({
  user: backupUser,
  pwd: backupPassword,
  roles: [{ role: "backup", db: "admin" }],
});
