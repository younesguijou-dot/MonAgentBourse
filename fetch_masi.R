suppressPackageStartupMessages(library(casabourse))

df <- masi.data()
write.csv(df, "masi.csv", row.names = FALSE)
cat("OK: masi.csv generated\n")
