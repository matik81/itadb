//! Experimental, immutable, snapshot-specific store. No SQL or write API.
use memmap2::Mmap;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::ffi::{CStr, CString, c_char};
use std::fs::{self, File};
use std::io::{BufReader, BufWriter, Read, Write};
use std::path::Path;
use std::time::Instant;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[derive(Serialize, Deserialize, Clone, Debug)]
struct Span {
    start: u32,
    end: u32,
}

#[derive(Serialize, Deserialize)]
struct Metadata {
    format: String,
    reference_year: u16,
    persons: u32,
    households: u32,
    person_spans: BTreeMap<u32, Span>,
    household_spans: BTreeMap<u32, Span>,
    cell_spans: BTreeMap<u32, Span>,
    files: BTreeMap<String, String>,
    build_seconds: f64,
    input_manifest_sha256: String,
}

fn u32_at(data: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(data[offset..offset + 4].try_into().unwrap())
}
fn u16_at(data: &[u8], offset: usize) -> u16 {
    u16::from_le_bytes(data[offset..offset + 2].try_into().unwrap())
}
fn hash_file(path: &Path) -> Result<String> {
    let mut reader = BufReader::new(File::open(path)?);
    let mut hash = Sha256::new();
    let mut buf = vec![0; 1024 * 1024];
    loop {
        let n = reader.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hash.update(&buf[..n]);
    }
    Ok(format!("{:x}", hash.finalize()))
}
fn rows(path: &Path) -> Result<csv::Reader<File>> {
    Ok(csv::ReaderBuilder::new()
        .has_headers(false)
        .from_path(path)?)
}
fn number(row: &csv::StringRecord, i: usize) -> Result<u32> {
    Ok(row.get(i).ok_or("missing column")?.parse()?)
}
fn span_add(spans: &mut BTreeMap<u32, Span>, code: u32, id: u32) -> Result<()> {
    if let Some(span) = spans.get_mut(&code) {
        if span.end != id {
            return Err("Municipality IDs are not contiguous".into());
        }
        span.end += 1;
    } else {
        spans.insert(
            code,
            Span {
                start: id,
                end: id + 1,
            },
        );
    }
    Ok(())
}
fn write_bytes(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut f = File::create_new(path)?;
    f.write_all(bytes)?;
    f.sync_all()?;
    Ok(())
}
fn write_u32(path: &Path, data: &[u32]) -> Result<()> {
    let mut writer = BufWriter::new(File::create_new(path)?);
    for value in data {
        writer.write_all(&value.to_le_bytes())?;
    }
    writer.flush()?;
    writer.get_ref().sync_all()?;
    Ok(())
}

/// Write into a new directory; manifest is the final, atomic publication marker.
pub fn build(input: &Path, output: &Path) -> Result<()> {
    let started = Instant::now();
    fs::create_dir(output)?;
    let mut household = Vec::new();
    let mut household_spans = BTreeMap::new();
    let mut offsets = Vec::new();
    let mut total_members = 0u32;
    for record in rows(&input.join("household.csv"))?.records() {
        let r = record?;
        let id = number(&r, 0)?;
        let muni = number(&r, 1)?;
        let size = number(&r, 2)?;
        if id as usize != household.len() / 12 + 1 || !(1..=6).contains(&size) {
            return Err("Invalid household ID or size".into());
        }
        span_add(&mut household_spans, muni, id)?;
        offsets.push(total_members);
        household.extend_from_slice(&total_members.to_le_bytes());
        household.extend_from_slice(&muni.to_le_bytes());
        household.extend_from_slice(&[size as u8, 0, 0, 0]);
        total_members = total_members.checked_add(size).ok_or("Too many members")?;
    }
    let households = (household.len() / 12) as u32;
    println!("Households: {households}; members: {total_members}");
    let mut members = vec![0u32; total_members as usize];
    let mut person = Vec::new();
    let mut person_spans = BTreeMap::new();
    for record in rows(&input.join("person.csv"))?.records() {
        let r = record?;
        let id = number(&r, 0)?;
        let hid = number(&r, 1)?;
        let muni = number(&r, 2)?;
        let sex = number(&r, 3)?;
        let age = number(&r, 4)?;
        let citizen = number(&r, 5)?;
        let adult = number(&r, 6)?;
        if id as usize != person.len() / 12 + 1
            || sex > 1
            || age > 100
            || citizen > 65535
            || adult > 1
            || hid > households
        {
            return Err("Invalid person fields or non-dense ID".into());
        }
        span_add(&mut person_spans, muni, id)?;
        person.extend_from_slice(&hid.to_le_bytes());
        person.extend_from_slice(&muni.to_le_bytes());
        person.extend_from_slice(&(citizen as u16).to_le_bytes());
        person.extend_from_slice(&[age as u8, (sex | adult << 1) as u8]);
        if hid != 0 {
            let h = (hid as usize - 1) * 12;
            if u32_at(&household, h + 4) != muni {
                return Err("Cross-municipality family".into());
            }
            let cursor = &mut offsets[hid as usize - 1];
            let end = u32_at(&household, h) + household[h + 8] as u32;
            if *cursor >= end {
                return Err("Too many household members".into());
            }
            members[*cursor as usize] = id;
            *cursor += 1;
        }
        if id % 10_000_000 == 0 {
            println!("Persons: {id}");
        }
    }
    for (i, cursor) in offsets.iter().enumerate() {
        if *cursor != u32_at(&household, i * 12) + household[i * 12 + 8] as u32 {
            return Err("Missing household members".into());
        }
    }
    let persons = (person.len() / 12) as u32;
    let mut age_index = vec![0u32; persons as usize];
    for span in person_spans.values() {
        let mut counts = [0u32; 101];
        for id in span.start..span.end {
            counts[person[(id as usize - 1) * 12 + 10] as usize] += 1;
        }
        let mut positions = [0u32; 101];
        let mut pos = span.start - 1;
        for age in (0..=100).rev() {
            positions[age] = pos;
            pos += counts[age];
        }
        for id in span.start..span.end {
            let age = person[(id as usize - 1) * 12 + 10] as usize;
            age_index[positions[age] as usize] = id;
            positions[age] += 1;
        }
    }
    write_bytes(&output.join("persons.bin"), &person)?;
    write_bytes(&output.join("households.bin"), &household)?;
    write_u32(&output.join("members.bin"), &members)?;
    write_u32(&output.join("age-index.bin"), &age_index)?;
    println!("Person, household and ordering indexes written");
    let mut cells = Vec::new();
    let mut cell_spans = BTreeMap::new();
    for record in rows(&input.join("cell.csv"))?.records() {
        let r = record?;
        let muni = number(&r, 0)?;
        let sex = number(&r, 1)?;
        let age = number(&r, 2)?;
        let citizen = number(&r, 3)?;
        let count = number(&r, 4)?;
        if sex > 1 || age > 100 || citizen > 65535 {
            return Err("Invalid cell".into());
        }
        span_add(&mut cell_spans, muni, (cells.len() / 12) as u32)?;
        cells.extend_from_slice(&muni.to_le_bytes());
        cells.extend_from_slice(&count.to_le_bytes());
        cells.extend_from_slice(&(citizen as u16).to_le_bytes());
        cells.extend_from_slice(&[age as u8, sex as u8]);
    }
    write_bytes(&output.join("cells.bin"), &cells)?;
    let mut files = BTreeMap::new();
    for name in [
        "persons.bin",
        "households.bin",
        "members.bin",
        "age-index.bin",
        "cells.bin",
    ] {
        files.insert(name.to_string(), hash_file(&output.join(name))?);
    }
    let metadata = Metadata {
        format: "itadb-consultation/1".into(),
        reference_year: 2025,
        persons,
        households,
        person_spans,
        household_spans,
        cell_spans,
        files,
        build_seconds: started.elapsed().as_secs_f64(),
        input_manifest_sha256: hash_file(&input.join("prepare-duckdb.json"))?,
    };
    write_bytes(
        &output.join("manifest.pending"),
        &serde_json::to_vec(&metadata)?,
    )?;
    fs::rename(
        output.join("manifest.pending"),
        output.join("manifest.json"),
    )?;
    File::open(output)?.sync_all()?;
    println!(
        "Published {persons} persons; {households} households in {:.2}s",
        started.elapsed().as_secs_f64()
    );
    Ok(())
}

pub struct Store {
    meta: Metadata,
    persons: Mmap,
    households: Mmap,
    members: Mmap,
    ages: Mmap,
    cells: Mmap,
}

/// Compare every decoded stored field against the canonical input CSVs.
pub fn audit(input: &Path, output: &Path) -> Result<()> {
    let store = Store::open(output, true)?;
    for table in ["person", "household", "cell"] {
        let mut hash = Sha256::new();
        let count = match table {
            "person" => store.meta.persons as usize,
            "household" => store.meta.households as usize,
            _ => store.cells.len() / 12,
        };
        for i in 0..count {
            let o = i * 12;
            let row = match table {
                "person" => format!(
                    "{},{},{},{},{},{},{}\n",
                    i + 1,
                    u32_at(&store.persons, o),
                    u32_at(&store.persons, o + 4),
                    store.persons[o + 11] & 1,
                    store.persons[o + 10],
                    u16_at(&store.persons, o + 8),
                    (store.persons[o + 11] >> 1) & 1
                ),
                "household" => format!(
                    "{},{},{}\n",
                    i + 1,
                    u32_at(&store.households, o + 4),
                    store.households[o + 8]
                ),
                _ => format!(
                    "{},{},{},{},{}\n",
                    u32_at(&store.cells, o),
                    store.cells[o + 11],
                    store.cells[o + 10],
                    u16_at(&store.cells, o + 8),
                    u32_at(&store.cells, o + 4)
                ),
            };
            hash.update(row.as_bytes());
        }
        let actual = format!("{:x}", hash.finalize());
        if actual != hash_file(&input.join(format!("{table}.csv")))? {
            return Err(format!("Full record parity failed: {table}").into());
        }
        println!("Full parity {table}: {count} records; sha256={actual}");
    }
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Query {
    op: String,
    #[serde(default)]
    id: u32,
    #[serde(default)]
    municipality: u32,
    #[serde(default)]
    sex: Option<String>,
    #[serde(default)]
    citizenship: Option<u16>,
    #[serde(default)]
    age_min: u8,
    #[serde(default = "max_age")]
    age_max: u8,
    #[serde(default = "default_sort")]
    sort: String,
    #[serde(default)]
    desc: bool,
    #[serde(default)]
    after: u32,
    #[serde(default = "default_limit")]
    limit: usize,
    #[serde(default)]
    size: Option<u8>,
}
fn max_age() -> u8 {
    100
}
fn default_sort() -> String {
    "id".into()
}
fn default_limit() -> usize {
    100
}

impl Store {
    pub fn open(path: &Path, verify: bool) -> Result<Self> {
        let meta: Metadata = serde_json::from_reader(File::open(path.join("manifest.json"))?)?;
        if meta.format != "itadb-consultation/1" || meta.reference_year != 2025 {
            return Err("Unsupported archive version".into());
        }
        let mmap = |name: &str, expected: usize| -> Result<Mmap> {
            if !meta.files.contains_key(name) {
                return Err("Missing checksum".into());
            }
            let file = File::open(path.join(name))?;
            if file.metadata()?.len() as usize != expected {
                return Err("Invalid file size".into());
            }
            if verify && hash_file(&path.join(name))? != meta.files[name] {
                return Err("Archive checksum mismatch".into());
            }
            // Safety: the caller must preserve immutable files for the mapping lifetime.
            Ok(unsafe { Mmap::map(&file)? })
        };
        let persons = mmap("persons.bin", meta.persons as usize * 12)?;
        let households = mmap("households.bin", meta.households as usize * 12)?;
        let ages = mmap("age-index.bin", meta.persons as usize * 4)?;
        let member_count: usize = (0..meta.households as usize)
            .map(|i| households[i * 12 + 8] as usize)
            .sum();
        let members = mmap("members.bin", member_count * 4)?;
        let cell_count = meta.cell_spans.values().map(|r| r.end).max().unwrap_or(0) as usize;
        let cells = mmap("cells.bin", cell_count * 12)?;
        Ok(Self {
            meta,
            persons,
            households,
            ages,
            members,
            cells,
        })
    }
    fn person(&self, id: u32) -> Value {
        if id == 0 || id > self.meta.persons {
            return Value::Null;
        }
        let o = (id as usize - 1) * 12;
        let hid = u32_at(&self.persons, o);
        let age = self.persons[o + 10];
        json!([
            id,
            if hid == 0 { None } else { Some(hid) },
            u32_at(&self.persons, o + 4),
            if self.persons[o + 11] & 1 == 0 {
                "F"
            } else {
                "M"
            },
            if age == 100 {
                None
            } else {
                Some(2024 - age as u16)
            },
            if age == 100 { Some(1924) } else { None },
            age,
            u16_at(&self.persons, o + 8),
            self.persons[o + 11] & 2 != 0
        ])
    }
    fn household(&self, id: u32) -> Value {
        if id == 0 || id > self.meta.households {
            return Value::Null;
        }
        let o = (id as usize - 1) * 12;
        json!([id, u32_at(&self.households, o + 4), self.households[o + 8]])
    }
    fn matches(&self, id: u32, q: &Query) -> bool {
        if id == 0 || id > self.meta.persons {
            return false;
        }
        let o = (id as usize - 1) * 12;
        let sex = if self.persons[o + 11] & 1 == 0 {
            "F"
        } else {
            "M"
        };
        u32_at(&self.persons, o + 4) == q.municipality
            && self.persons[o + 10] >= q.age_min
            && self.persons[o + 10] <= q.age_max
            && q.sex.as_ref().is_none_or(|s| s == sex)
            && q.citizenship
                .is_none_or(|c| c == u16_at(&self.persons, o + 8))
    }
    fn sort_value(&self, id: u32, sort: &str) -> u32 {
        let o = (id as usize - 1) * 12;
        match sort {
            "age" => self.persons[o + 10] as u32,
            "sex" => (self.persons[o + 11] & 1) as u32,
            "citizenship" => u16_at(&self.persons, o + 8) as u32,
            "household" => u32_at(&self.persons, o),
            _ => id,
        }
    }
    fn query(&self, q: Query) -> Result<Value> {
        if q.limit == 0 || q.limit > 500 || q.age_min > q.age_max || q.age_max > 100 {
            return Err("Invalid query bounds".into());
        }
        match q.op.as_str() {
            "person" => Ok(self.person(q.id)),
            "household" => {
                let household = self.household(q.id);
                if household.is_null() {
                    return Ok(Value::Null);
                }
                let o = (q.id as usize - 1) * 12;
                let start = u32_at(&self.households, o);
                let count = self.households[o + 8] as u32;
                let members: Vec<Value> = (start..start + count)
                    .map(|i| self.person(u32_at(&self.members, i as usize * 4)))
                    .collect();
                Ok(json!({"household": household, "members": members}))
            }
            "persons" => {
                if !["id", "age", "sex", "citizenship", "household"].contains(&q.sort.as_str()) {
                    return Err("Unsupported ordering".into());
                }
                let Some(span) = self.meta.person_spans.get(&q.municipality) else {
                    return Ok(json!([]));
                };
                if q.after != 0 && !self.matches(q.after, &q) {
                    return Ok(json!([]));
                }
                let anchor = if q.after == 0 {
                    0
                } else {
                    self.sort_value(q.after, &q.sort)
                };
                let accepted = |id: &u32| {
                    if !self.matches(*id, &q) {
                        return false;
                    }
                    if q.after == 0 {
                        return true;
                    }
                    let s = self.sort_value(*id, &q.sort);
                    (if q.desc { s < anchor } else { s > anchor }) || (s == anchor && *id > q.after)
                };
                let ids: Vec<u32> = if q.sort == "id" && !q.desc {
                    (span.start.max(q.after.saturating_add(1))..span.end)
                        .filter(accepted)
                        .take(q.limit)
                        .collect()
                } else if q.sort == "age" && q.desc {
                    (span.start - 1..span.end - 1)
                        .map(|i| u32_at(&self.ages, i as usize * 4))
                        .filter(accepted)
                        .take(q.limit)
                        .collect()
                } else {
                    let mut ids: Vec<u32> = (span.start..span.end).filter(accepted).collect();
                    let key = |id: &u32| {
                        let s = self.sort_value(*id, &q.sort);
                        (if q.desc { u32::MAX - s } else { s }, *id)
                    };
                    if ids.len() > q.limit {
                        ids.select_nth_unstable_by_key(q.limit, key);
                        ids.truncate(q.limit);
                    }
                    ids.sort_unstable_by_key(key);
                    ids
                };
                Ok(Value::Array(
                    ids.into_iter().map(|id| self.person(id)).collect(),
                ))
            }
            "households" => {
                if q.sort != "id" && q.sort != "size" {
                    return Err("Unsupported ordering".into());
                }
                let Some(span) = self.meta.household_spans.get(&q.municipality) else {
                    return Ok(json!([]));
                };
                let accepted = |id: u32| {
                    span.start <= id
                        && id < span.end
                        && q.size
                            .is_none_or(|s| self.households[(id as usize - 1) * 12 + 8] == s)
                };
                if q.after != 0 && !accepted(q.after) {
                    return Ok(json!([]));
                }
                let sort = |id: u32| {
                    if q.sort == "size" {
                        self.households[(id as usize - 1) * 12 + 8] as u32
                    } else {
                        id
                    }
                };
                let anchor = if q.after == 0 { 0 } else { sort(q.after) };
                let mut ids: Vec<u32> = (span.start..span.end)
                    .filter(|id| {
                        accepted(*id)
                            && (q.after == 0
                                || (if q.desc {
                                    sort(*id) < anchor
                                } else {
                                    sort(*id) > anchor
                                })
                                || (sort(*id) == anchor && *id > q.after))
                    })
                    .collect();
                let key = |id: &u32| {
                    (
                        if q.desc {
                            u32::MAX - sort(*id)
                        } else {
                            sort(*id)
                        },
                        *id,
                    )
                };
                if ids.len() > q.limit {
                    ids.select_nth_unstable_by_key(q.limit, key);
                    ids.truncate(q.limit);
                }
                ids.sort_unstable_by_key(key);
                Ok(Value::Array(
                    ids.into_iter().map(|id| self.household(id)).collect(),
                ))
            }
            "distribution" => {
                let range = if q.municipality == 0 {
                    0..(self.cells.len() / 12) as u32
                } else if let Some(s) = self.meta.cell_spans.get(&q.municipality) {
                    s.start..s.end
                } else {
                    0..0
                };
                let mut counts = [0u64; 202];
                for i in range {
                    let o = i as usize * 12;
                    let age = self.cells[o + 10];
                    let sex = self.cells[o + 11];
                    if age >= q.age_min
                        && age <= q.age_max
                        && q.sex
                            .as_ref()
                            .is_none_or(|s| s == if sex == 0 { "F" } else { "M" })
                        && q.citizenship
                            .is_none_or(|c| c == u16_at(&self.cells, o + 8))
                    {
                        counts[age as usize * 2 + sex as usize] +=
                            u32_at(&self.cells, o + 4) as u64;
                    }
                }
                Ok(Value::Array(
                    counts
                        .iter()
                        .enumerate()
                        .filter(|(_, n)| **n > 0)
                        .map(|(i, n)| json!([i / 2, if i % 2 == 0 { "F" } else { "M" }, n]))
                        .collect(),
                ))
            }
            _ => Err("Unsupported operation".into()),
        }
    }
}

/// # Safety
/// `path` must point to a valid NUL-terminated UTF-8 string; archive files must remain immutable.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn store_open(path: *const c_char) -> *mut Store {
    std::panic::catch_unwind(|| {
        let path = unsafe { CStr::from_ptr(path) }.to_str().ok()?;
        Store::open(Path::new(path), true)
            .ok()
            .map(|s| Box::into_raw(Box::new(s)))
    })
    .ok()
    .flatten()
    .unwrap_or(std::ptr::null_mut())
}
/// # Safety
/// `store` is a live handle returned by store_open; `query` is a valid NUL-terminated string.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn store_query(store: *const Store, query: *const c_char) -> *mut c_char {
    let result = std::panic::catch_unwind(|| -> Result<Value> {
        let q: Query = serde_json::from_slice(unsafe { CStr::from_ptr(query) }.to_bytes())?;
        unsafe { &*store }.query(q)
    });
    let value = match result {
        Ok(Ok(v)) => v,
        Ok(Err(e)) => json!({"error":e.to_string()}),
        Err(_) => json!({"error":"Archive or query invariant violated"}),
    };
    CString::new(value.to_string()).unwrap().into_raw()
}
/// # Safety
/// `value` was allocated by store_query and is freed exactly once.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn store_free(value: *mut c_char) {
    if !value.is_null() {
        drop(unsafe { CString::from_raw(value) });
    }
}
/// # Safety
/// `store` was allocated by store_open, is closed once, and has no in-flight queries.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn store_close(store: *mut Store) {
    if !store.is_null() {
        drop(unsafe { Box::from_raw(store) });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn little_endian_fields() {
        assert_eq!(u32_at(&[1, 2, 3, 4], 0), 0x04030201);
        assert_eq!(u16_at(&[1, 2], 0), 513);
    }
    #[test]
    fn noncontiguous_municipality_is_rejected() {
        let mut spans = BTreeMap::new();
        span_add(&mut spans, 42, 1).unwrap();
        assert!(span_add(&mut spans, 42, 3).is_err());
    }

    #[test]
    fn lifecycle_queries_and_corruption() {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("itadb-store-test-{unique}"));
        fs::create_dir(&root).unwrap();
        fs::write(root.join("prepare-duckdb.json"), "{}").unwrap();
        fs::write(root.join("household.csv"), "1,10,2\n2,20,1\n").unwrap();
        fs::write(
            root.join("person.csv"),
            "1,1,10,0,100,100,1\n2,1,10,1,20,201,0\n3,0,10,0,100,100,0\n4,2,20,1,40,100,1\n",
        )
        .unwrap();
        fs::write(
            root.join("cell.csv"),
            "10,1,20,201,1\n10,0,100,100,2\n20,1,40,100,1\n",
        )
        .unwrap();
        let output = root.join("store");
        build(&root, &output).unwrap();
        assert!(build(&root, &output).is_err());
        audit(&root, &output).unwrap();
        let store = Store::open(&output, true).unwrap();
        let query = |q: Value| store.query(serde_json::from_value(q).unwrap()).unwrap();
        assert_eq!(query(json!({"op":"person","id":1}))[4], Value::Null);
        assert_eq!(query(json!({"op":"person","id":1}))[5], 1924);
        assert_eq!(query(json!({"op":"person","id":3}))[1], Value::Null);
        assert_eq!(query(json!({"op":"person","id":99})), Value::Null);
        assert_eq!(
            query(json!({"op":"household","id":1}))["members"]
                .as_array()
                .unwrap()
                .len(),
            2
        );
        let p = query(json!({"op":"persons","municipality":10,"sort":"age","desc":true,"after":1}));
        assert_eq!(p[0][0], 3);
        assert_eq!(p[1][0], 2);
        assert_eq!(
            query(json!({"op":"persons","municipality":10,"after":1,"sex":"M"})),
            json!([])
        );
        assert_eq!(
            query(json!({"op":"persons","municipality":10,"sort":"age","after":2}))[0][0],
            1
        );
        assert_eq!(
            query(json!({"op":"distribution","citizenship":100})),
            json!([[40, "M", 1], [100, "F", 2]])
        );
        assert!(
            store
                .query(serde_json::from_value(json!({"op":"persons","limit":501})).unwrap())
                .is_err()
        );
        drop(store);
        let mut bytes = fs::read(output.join("persons.bin")).unwrap();
        bytes[0] ^= 1;
        fs::write(output.join("persons.bin"), bytes).unwrap();
        assert!(Store::open(&output, true).is_err());
        fs::write(root.join("person.csv"), "2,1,10,0,30,100,1\n").unwrap();
        let failed = root.join("failed");
        assert!(build(&root, &failed).is_err());
        assert!(!failed.join("manifest.json").exists());
        assert!(Store::open(&failed, true).is_err());
        // Only generated test fixtures are removed; real experiment evidence is preserved.
        fs::remove_dir_all(root).unwrap();
    }
}
