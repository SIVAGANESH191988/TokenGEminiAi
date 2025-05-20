import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Container, Tabs, Tab, Box, Typography, Button, TextField, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, CircularProgress } from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';

function App() {
  const [tabValue, setTabValue] = useState(0);
  const [files, setFiles] = useState([]);
  const [results, setResults] = useState([]);
  const [totalTokens, setTotalTokens] = useState(0);
  const [recordIds, setRecordIds] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [record, setRecord] = useState(null);
  const [allRecords, setAllRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Handle tab change
  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
    if (newValue === 1 && recordIds.length === 0) {
      fetchRecordIds();
    }
  };

  // Handle file selection
  const handleFileChange = (event) => {
    setFiles(event.target.files);
  };

  // Upload and process files
  const handleUpload = async () => {
    if (files.length === 0) {
      setError('Please select at least one file.');
      return;
    }
    setLoading(true);
    setError('');
    const formData = new FormData();
    Array.from(files).forEach(file => formData.append('files', file));
    
    try {
      const response = await axios.post('http://localhost:8000/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setResults(response.data.results);
      setTotalTokens(response.data.total_tokens);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error processing files.');
    } finally {
      setLoading(false);
    }
  };

  // Fetch record IDs
  const fetchRecordIds = async () => {
    try {
      const response = await axios.get('http://localhost:8000/records');
      setRecordIds(response.data.ids);
    } catch (err) {
      setError('Error fetching record IDs.');
    }
  };

  // Fetch record by ID
  const fetchRecord = async () => {
    if (!selectedId) {
      setError('Please select a record ID.');
      setRecord(null);
      return;
    }
    setLoading(true);
    setError('');
    setAllRecords([]);
    try {
      const response = await axios.get(`http://localhost:8000/record/${selectedId}`);
      setRecord(response.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error fetching record.');
      setRecord(null);
    } finally {
      setLoading(false);
    }
  };

  // Fetch all records
  const fetchAllRecords = async () => {
    setLoading(true);
    setError('');
    setRecord(null);
    try {
      const response = await axios.get('http://localhost:8000/all_records');
      setAllRecords(response.data.records);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error fetching all records.');
      setAllRecords([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="lg" style={{ padding: '20px' }}>
      <Typography variant="h4" gutterBottom>
        📄 Gemini Document Extractor
      </Typography>
      <Tabs value={tabValue} onChange={handleTabChange} centered>
        <Tab label="Upload Documents" />
        <Tab label="View Records" />
      </Tabs>

      {/* Upload Documents Tab */}
      {tabValue === 0 && (
        <Box mt={4}>
          <Typography variant="h6">Upload your documents:</Typography>
          <TextField
            type="file"
            inputProps={{ multiple: true, accept: '.msg,.txt,.pdf,.docx,.jpg,.png,.jpeg' }}
            onChange={handleFileChange}
            fullWidth
            margin="normal"
          />
          <Button
            variant="contained"
            color="primary"
            startIcon={<CloudUploadIcon />}
            onClick={handleUpload}
            disabled={loading}
          >
            {loading ? <CircularProgress size={24} /> : 'Process Files'}
          </Button>
          {error && <Typography color="error" mt={2}>{error}</Typography>}
          {results.length > 0 && (
            <Box mt={4}>
              <Typography variant="h6">Results:</Typography>
              {results.map((result, index) => (
                <Box key={index} mb={2}>
                  <Typography><strong>File:</strong> {result.filename}</Typography>
                  <Typography><strong>Intent:</strong> {result.intent}</Typography>
                  {result.extracted_data && (
                    <>
                      <Typography mt={2}><strong>Extracted Data (JSON):</strong></Typography>
                      <Paper style={{ padding: '10px', maxHeight: '400px', overflow: 'auto', backgroundColor: '#1e1e1e', color: '#ffffff' }}>
                        <pre style={{ margin: 0, fontSize: '14px' }}>
                          {JSON.stringify(result.extracted_data, null, 2)}
                        </pre>
                      </Paper>
                    </>
                  )}
                  <Typography><strong>Tokens Used:</strong> {result.tokens_used}</Typography>
                  <Typography><strong>Stored in DB:</strong> {result.stored ? 'Yes' : 'No'}</Typography>
                </Box>
              ))}
              <Typography><strong>Total Session Tokens:</strong> {totalTokens}</Typography>
            </Box>
          )}
        </Box>
      )}

      {/* View Records Tab */}
      {tabValue === 1 && (
        <Box mt={4}>
          <Typography variant="h6">View Stored Records</Typography>
          <Box display="flex" gap={2} alignItems="center">
            <TextField
              select
              label="Select Record ID"
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              style={{ minWidth: '200px' }}
              margin="normal"
              SelectProps={{ native: true }}
            >
              <option value="">Select an ID</option>
              {recordIds.map(id => (
                <option key={id} value={id}>{id}</option>
              ))}
            </TextField>
            <Button
              variant="contained"
              color="primary"
              onClick={fetchRecord}
              disabled={loading}
            >
              {loading ? <CircularProgress size={24} /> : 'View Record'}
            </Button>
            <Button
              variant="contained"
              color="secondary"
              onClick={fetchAllRecords}
              disabled={loading}
            >
              {loading ? <CircularProgress size={24} /> : 'View All Records'}
            </Button>
          </Box>
          {error && <Typography color="error" mt={2}>{error}</Typography>}
          <Box mt={2}>
            <Typography><strong>Selected Record:</strong></Typography>
            <Box component="form" mt={2}>
              <TextField
                label="Name"
                value={record ? record.name : ''}
                InputProps={{ readOnly: true }}
                fullWidth
                margin="normal"
              />
              <TextField
                label="Email"
                value={record ? record.email : ''}
                InputProps={{ readOnly: true }}
                fullWidth
                margin="normal"
              />
              <TextField
                label="Number"
                value={record ? record.number : ''}
                InputProps={{ readOnly: true }}
                fullWidth
                margin="normal"
              />
              <TextField
                label="Professional Summary"
                value={record ? record.professional_summary : ''}
                InputProps={{ readOnly: true }}
                fullWidth
                margin="normal"
                multiline
                rows={4}
              />
              <TextField
                label="Project Name"
                value={record ? record.project_name : ''}
                InputProps={{ readOnly: true }}
                fullWidth
                margin="normal"
              />
              <TextField
                label="Skills"
                value={record ? record.skills : ''}
                InputProps={{ readOnly: true }}
                fullWidth
                margin="normal"
              />
            </Box>
          </Box>
          {allRecords.length > 0 && (
            <Box mt={2}>
              <Typography><strong>All Records:</strong></Typography>
              <TableContainer component={Paper}>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>ID</TableCell>
                      <TableCell>Name</TableCell>
                      <TableCell>Email</TableCell>
                      <TableCell>Number</TableCell>
                      <TableCell>Professional Summary</TableCell>
                      <TableCell>Project Name</TableCell>
                      <TableCell>Skills</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {allRecords.map((rec, idx) => (
                      <TableRow key={idx}>
                        <TableCell>{rec.id}</TableCell>
                        <TableCell>{rec.name}</TableCell>
                        <TableCell>{rec.email}</TableCell>
                        <TableCell>{rec.number}</TableCell>
                        <TableCell>{rec.professional_summary}</TableCell>
                        <TableCell>{rec.project_name}</TableCell>
                        <TableCell>{rec.skills}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}
        </Box>
      )}
    </Container>
  );
}

export default App;