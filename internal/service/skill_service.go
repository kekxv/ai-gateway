package service

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/kekxv/ai-gateway/internal/models"
	"github.com/kekxv/ai-gateway/internal/repository"
)

var (
	ErrSkillNotFound     = errors.New("skill not found")
	ErrSkillNameExists   = errors.New("skill name already exists")
	ErrInvalidSkillMD    = errors.New("invalid SKILL.md format")
)

// SkillFrontmatter represents parsed YAML frontmatter from SKILL.md
type SkillFrontmatter struct {
	Name         string                 `yaml:"name"`
	Description  string                 `yaml:"description"`
	License      string                 `yaml:"license,omitempty"`
	Compatibility string                 `yaml:"compatibility,omitempty"`
	Metadata     map[string]interface{} `yaml:"metadata,omitempty"`
	AllowedTools string                 `yaml:"allowed-tools,omitempty"`
}

// SkillService handles skill-related business logic
type SkillService struct {
	skillRepo *repository.SkillRepository
	userRepo  *repository.UserRepository
}

func NewSkillService(skillRepo *repository.SkillRepository, userRepo *repository.UserRepository) *SkillService {
	return &SkillService{
		skillRepo: skillRepo,
		userRepo:  userRepo,
	}
}

// CreateSkill creates a new skill from request
func (s *SkillService) CreateSkill(ctx context.Context, userID uint, req *models.CreateSkillRequest) (*models.Skill, error) {
	// Check if name already exists for this user
	existing, err := s.skillRepo.FindByName(ctx, userID, req.Name)
	if err == nil && existing != nil {
		return nil, ErrSkillNameExists
	}

	skill := &models.Skill{
		UserID:        userID,
		Name:          req.Name,
		DisplayName:   req.DisplayName,
		Description:   req.Description,
		Location:      req.Location,
		Instructions:  req.Instructions,
		License:       req.License,
		Compatibility: req.Compatibility,
		Metadata:      req.Metadata,
		AllowedTools:  req.AllowedTools,
		Source:        req.Source,
		Enabled:       req.Enabled,
	}

	if skill.Source == "" {
		skill.Source = "database"
	}

	if err := s.skillRepo.Create(ctx, skill); err != nil {
		return nil, err
	}

	return skill, nil
}

// UpdateSkill updates an existing skill
func (s *SkillService) UpdateSkill(ctx context.Context, userID uint, skillID uint, req *models.UpdateSkillRequest) (*models.Skill, error) {
	skill, err := s.skillRepo.FindByID(ctx, skillID)
	if err != nil {
		return nil, ErrSkillNotFound
	}

	// Check ownership
	if skill.UserID != userID {
		return nil, ErrPermissionDenied
	}

	// Update fields
	if req.DisplayName != "" {
		skill.DisplayName = req.DisplayName
	}
	if req.Description != "" {
		skill.Description = req.Description
	}
	skill.Instructions = req.Instructions
	skill.License = req.License
	skill.Compatibility = req.Compatibility
	skill.Metadata = req.Metadata
	skill.AllowedTools = req.AllowedTools
	skill.Enabled = req.Enabled

	if err := s.skillRepo.Update(ctx, skill); err != nil {
		return nil, err
	}

	return skill, nil
}

// DeleteSkill deletes a skill
func (s *SkillService) DeleteSkill(ctx context.Context, userID uint, skillID uint) error {
	skill, err := s.skillRepo.FindByID(ctx, skillID)
	if err != nil {
		return ErrSkillNotFound
	}

	if skill.UserID != userID {
		return ErrPermissionDenied
	}

	return s.skillRepo.Delete(ctx, skillID)
}

// GetSkill retrieves a skill with its resources
func (s *SkillService) GetSkill(ctx context.Context, userID uint, skillID uint) (*models.Skill, error) {
	skill, err := s.skillRepo.FindByIDWithResources(ctx, skillID)
	if err != nil {
		return nil, ErrSkillNotFound
	}

	if skill.UserID != userID {
		return nil, ErrPermissionDenied
	}

	return skill, nil
}

// ListSkills lists all skills for a user
func (s *SkillService) ListSkills(ctx context.Context, userID uint) ([]models.Skill, error) {
	return s.skillRepo.List(ctx, userID)
}

// GetCatalog returns the skills catalog for chat integration
func (s *SkillService) GetCatalog(ctx context.Context, userID uint) ([]models.SkillCatalogItem, error) {
	return s.skillRepo.GetCatalog(ctx, userID)
}

// GenerateSkillsXML generates the XML format for chat prompt
func (s *SkillService) GenerateSkillsXML(catalog []models.SkillCatalogItem) string {
	// Count enabled skills first
	enabledCount := 0
	for _, item := range catalog {
		if item.Enabled {
			enabledCount++
		}
	}

	// Return empty string if no enabled skills
	if enabledCount == 0 {
		return ""
	}

	var sb strings.Builder
	sb.WriteString("<available_skills>\n")
	for _, item := range catalog {
		if item.Enabled {
			sb.WriteString("  <skill>\n")
			sb.WriteString(fmt.Sprintf("    <name>%s</name>\n", escapeXML(item.Name)))
			sb.WriteString(fmt.Sprintf("    <description>%s</description>\n", escapeXML(item.Description)))
			sb.WriteString(fmt.Sprintf("    <location>%s</location>\n", escapeXML(item.Location)))
			sb.WriteString("  </skill>\n")
		}
	}
	sb.WriteString("</available_skills>")
	return sb.String()
}

// escapeXML escapes special characters for XML content
func escapeXML(s string) string {
	s = strings.ReplaceAll(s, "&", "&amp;")
	s = strings.ReplaceAll(s, "<", "&lt;")
	s = strings.ReplaceAll(s, ">", "&gt;")
	s = strings.ReplaceAll(s, "\"", "&quot;")
	s = strings.ReplaceAll(s, "'", "&apos;")
	return s
}

// ToggleSkill toggles the enabled status of a skill
func (s *SkillService) ToggleSkill(ctx context.Context, userID uint, skillID uint) (*models.Skill, error) {
	skill, err := s.skillRepo.FindByID(ctx, skillID)
	if err != nil {
		return nil, ErrSkillNotFound
	}

	if skill.UserID != userID {
		return nil, ErrPermissionDenied
	}

	skill.Enabled = !skill.Enabled

	if err := s.skillRepo.Update(ctx, skill); err != nil {
		return nil, err
	}

	return skill, nil
}

// ScanLocalSkills scans local directories for skills following agentskills.io standard
func (s *SkillService) ScanLocalSkills(ctx context.Context, userID uint, projectPath string) ([]models.Skill, error) {
	var skills []models.Skill

	// Scan project-level: <project>/.agents/skills/
	if projectPath != "" {
		projectSkillsPath := filepath.Join(projectPath, ".agents", "skills")
		if _, err := os.Stat(projectSkillsPath); err == nil {
			projectSkills, err := s.scanSkillsDirectory(ctx, userID, projectSkillsPath, "local")
			if err != nil {
				return nil, err
			}
			skills = append(skills, projectSkills...)
		}
	}

	// Scan user-level: ~/.agents/skills/
	homeDir, err := os.UserHomeDir()
	if err == nil {
		userSkillsPath := filepath.Join(homeDir, ".agents", "skills")
		if _, err := os.Stat(userSkillsPath); err == nil {
			userSkills, err := s.scanSkillsDirectory(ctx, userID, userSkillsPath, "local")
			if err != nil {
				return nil, err
			}
			skills = append(skills, userSkills...)
		}
	}

	return skills, nil
}

// scanSkillsDirectory scans a directory for skill folders containing SKILL.md
func (s *SkillService) scanSkillsDirectory(ctx context.Context, userID uint, dirPath string, source string) ([]models.Skill, error) {
	var skills []models.Skill

	entries, err := os.ReadDir(dirPath)
	if err != nil {
		return nil, err
	}

	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		skillPath := filepath.Join(dirPath, entry.Name())
		skillMDPath := filepath.Join(skillPath, "SKILL.md")

		if _, err := os.Stat(skillMDPath); err != nil {
			continue // Skip folders without SKILL.md
		}

		// Parse SKILL.md
		skill, err := s.parseSkillMD(ctx, userID, skillMDPath, skillPath, entry.Name(), source)
		if err != nil {
			continue // Skip invalid skills
		}

		skills = append(skills, *skill)
	}

	return skills, nil
}

// parseSkillMD parses a SKILL.md file following agentskills.io format
func (s *SkillService) parseSkillMD(ctx context.Context, userID uint, mdPath string, skillPath string, dirName string, source string) (*models.Skill, error) {
	content, err := os.ReadFile(mdPath)
	if err != nil {
		return nil, err
	}

	// Parse YAML frontmatter and markdown body
	frontmatter, body := parseFrontmatter(string(content))

	// Validate required fields
	if frontmatter.Name == "" {
		frontmatter.Name = dirName // Use directory name if not specified
	}
	if frontmatter.Description == "" {
		return nil, ErrInvalidSkillMD
	}

	// Build skill
	skill := &models.Skill{
		UserID:       userID,
		Name:         frontmatter.Name,
		Description:  frontmatter.Description,
		Location:     mdPath,
		Instructions: body,
		License:      frontmatter.License,
		Source:       source,
		Enabled:      true,
	}

	return skill, nil
}

// parseFrontmatter extracts YAML frontmatter and markdown body from content
func parseFrontmatter(content string) (SkillFrontmatter, string) {
	var frontmatter SkillFrontmatter
	var body string

	// Regex to match YAML frontmatter between --- markers
	re := regexp.MustCompile(`^---\s*\n(.*?)\n---\s*\n?(.*)$`)
	matches := re.FindStringSubmatch(content)

	if len(matches) < 3 {
		// No frontmatter found - treat entire content as body
		return frontmatter, content
	}

	yamlContent := matches[1]
	body = matches[2]

	// Parse YAML using regex-based parsing for basic fields
	frontmatter.Name = extractYAMLField(yamlContent, "name")
	frontmatter.Description = extractYAMLField(yamlContent, "description")
	frontmatter.License = extractYAMLField(yamlContent, "license")
	frontmatter.Compatibility = extractYAMLField(yamlContent, "compatibility")
	frontmatter.AllowedTools = extractYAMLField(yamlContent, "allowed-tools")

	return frontmatter, body
}

// extractYAMLField extracts a simple string field from YAML content
func extractYAMLField(yamlContent string, fieldName string) string {
	// Match both "field: value" and "field: "value"" formats
	re := regexp.MustCompile(fmt.Sprintf(`(?i)%s:\s*["']?([^"'\n]+)["']?`, fieldName))
	matches := re.FindStringSubmatch(yamlContent)
	if len(matches) > 1 {
		return strings.TrimSpace(matches[1])
	}
	return ""
}

// ImportLocalSkill imports a local skill into the database
func (s *SkillService) ImportLocalSkill(ctx context.Context, userID uint, skillPath string) (*models.Skill, error) {
	// Parse the skill from local directory
	skill, err := s.parseSkillMD(ctx, userID,
		filepath.Join(skillPath, "SKILL.md"),
		skillPath,
		filepath.Base(skillPath),
		"local")
	if err != nil {
		return nil, err
	}

	// Check if skill already exists
	existing, err := s.skillRepo.FindByName(ctx, userID, skill.Name)
	if err == nil && existing != nil {
		// Update existing skill
		existing.Description = skill.Description
		existing.Instructions = skill.Instructions
		existing.Location = skill.Location
		existing.License = skill.License
		existing.Source = "database" // Imported skills become database-managed
		s.skillRepo.Update(ctx, existing)
		return existing, nil
	}

	// Create new skill
	skill.Source = "database" // Imported skills become database-managed
	if err := s.skillRepo.Create(ctx, skill); err != nil {
		return nil, err
	}

	// Load resources
	s.loadSkillResources(ctx, skill.ID, skillPath)

	return skill, nil
}

// loadSkillResources loads scripts, references, and assets from skill directory
func (s *SkillService) loadSkillResources(ctx context.Context, skillID uint, skillPath string) error {
	resourceDirs := map[string]string{
		"scripts":    "script",
		"references": "reference",
		"assets":     "asset",
	}

	for dirName, resourceType := range resourceDirs {
		resourcePath := filepath.Join(skillPath, dirName)
		if _, err := os.Stat(resourcePath); err != nil {
			continue
		}

		err := filepath.WalkDir(resourcePath, func(path string, d fs.DirEntry, err error) error {
			if err != nil || d.IsDir() {
				return nil
			}

			content, err := os.ReadFile(path)
			if err != nil {
				return nil
			}

			// Only inline small files (< 50KB)
			var contentStr string
			if len(content) < 50*1024 {
				contentStr = string(content)
			}

			resource := &models.SkillResource{
				SkillID: skillID,
				Type:    resourceType,
				Name:    d.Name(),
				Path:    path,
				Content: contentStr,
			}

			return s.skillRepo.CreateResource(ctx, resource)
		})
		if err != nil {
			return err
		}
	}

	return nil
}